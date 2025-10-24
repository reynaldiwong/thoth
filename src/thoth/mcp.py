

import json
import subprocess
import time
from pathlib import Path
from typing import Optional, Dict, Any, List
from rich.prompt import Confirm
from rich.panel import Panel
from rich.table import Table
from rich.spinner import Spinner
from rich.live import Live
from prompt_toolkit import prompt
from prompt_toolkit.formatted_text import HTML
from .display import console, select_with_arrows
from .crypto import encrypt_value, decrypt_value
from .mcp_client import MCPManager, MCPConnection

MCP_CONFIG_PATH = Path.home() / ".thoth_mcp_config.json"


_mcp_manager: Optional[MCPManager] = None


def get_mcp_manager() -> MCPManager:
    
    global _mcp_manager
    if _mcp_manager is None:
        _mcp_manager = MCPManager()
    return _mcp_manager


class MCPServer:
    
    
    def __init__(self, name: str, command: str, args: List[str], env: Optional[Dict[str, str]] = None):
        self.name = name
        self.command = command
        self.args = args
        self.env = env or {}


def load_mcp_config() -> Dict[str, Any]:
    
    if not MCP_CONFIG_PATH.exists():
        return {"servers": {}}
    
    try:
        data = json.loads(MCP_CONFIG_PATH.read_text(encoding="utf-8"))
        
        for server_name, server_config in data.get("servers", {}).items():
            if "env" in server_config:
                for key, value in server_config["env"].items():
                    if value.startswith("encrypted:"):
                        server_config["env"][key] = decrypt_value(value[10:])
        return data
    except Exception as e:
        console.print(f"[red]Error loading MCP config: {e}[/red]")
        return {"servers": {}}


def save_mcp_config(config: Dict[str, Any]) -> None:
    
    
    config_copy = json.loads(json.dumps(config))  
    for server_name, server_config in config_copy.get("servers", {}).items():
        if "env" in server_config:
            for key, value in server_config["env"].items():
                if any(sensitive in key.upper() for sensitive in ["KEY", "SECRET", "TOKEN", "PASSWORD"]):
                    server_config["env"][key] = f"encrypted:{encrypt_value(value)}"
    
    MCP_CONFIG_PATH.write_text(json.dumps(config_copy, indent=2), encoding="utf-8")
    MCP_CONFIG_PATH.chmod(0o600)


def initialize_mcp_servers() -> None:
    
    config = load_mcp_config()
    servers = config.get("servers", {})
    
    if not servers:
        return
    
    manager = get_mcp_manager()
    
    for name, server_config in servers.items():
        
        enabled = server_config.get("enabled", True)
        
        if not enabled:
            console.print(f"[dim]Skipping disabled MCP server: {name}[/dim]")
            continue
        
        command = server_config.get("command", "")
        args = server_config.get("args", [])
        env = server_config.get("env", {})
        
        if command:
            console.print(f"[dim]Starting MCP server: {name}...[/dim]")
            if manager.start_server(name, transport="stdio", command=command, args=args, env=env):
                console.print(f"[green]✓ MCP server '{name}' connected[/green]")
            else:
                console.print(f"[yellow]⚠ Failed to connect to MCP server '{name}'[/yellow]")


def shutdown_mcp_servers() -> None:
    
    manager = get_mcp_manager()
    manager.stop_all()


def add_mcp_server_interactive() -> Optional[MCPServer]:
    
    console.print("\n[bold cyan]➕ Add MCP Server[/bold cyan]\n")
    
    
    name = prompt(HTML("<b>Server name</b> (e.g., 'filesystem', 'github'): ")).strip()
    if not name:
        console.print("[yellow]Server name is required[/yellow]")
        return None
    
    
    console.print("\n[dim]Examples:[/dim]")
    console.print("[dim]  • npx -y @modelcontextprotocol/server-filesystem /path/to/dir[/dim]")
    console.print("[dim]  • npx -y @google-cloud/gcloud-mcp[/dim]")
    console.print("[dim]  • npx -y @modelcontextprotocol/server-github[/dim]")
    console.print("[dim]  • python -m mcp_server_git[/dim]\n")
    
    command = prompt(HTML("<b>Command to run MCP server</b>: ")).strip()
    if not command:
        console.print("[yellow]Command is required[/yellow]")
        return None
    
    args_input = prompt(
        HTML("<b>Arguments</b> (space-separated, or press Enter to skip): "),
        default=""
    ).strip()
    args = args_input.split() if args_input else []
    
    
    env = {}
    console.print("\n[bold]Environment Variables[/bold] (optional)")
    console.print("[dim]Press Enter with empty key to finish[/dim]\n")
    
    while True:
        key = prompt("  Variable name: ", default="").strip()
        if not key:
            break
        
        is_sensitive = any(s in key.upper() for s in ["KEY", "SECRET", "TOKEN", "PASSWORD"])
        value = prompt(f"  Value for {key}: ", is_password=is_sensitive).strip()
        
        if value:
            env[key] = value
    
    return MCPServer(name, command, args, env)


def configure_mcp_interactive() -> None:
    
    config = load_mcp_config()
    
    while True:
        console.print("\n[bold cyan]🔧 MCP Configuration[/bold cyan]\n")
        
        options = {
            "Add Server": "add",
            "List Servers": "list",
            "Toggle Server (On/Off)": "toggle",  
            "Remove Server": "remove",
            "Test Connection": "test",
            "Back": "back"
        }
        
        choice = select_with_arrows(options, prompt_text="MCP Configuration Menu")
        
        if not choice or choice == "Back":
            break
        
        action = options[choice]
        
        if action == "add":
            server = add_mcp_server_interactive()
            if server:
                if "servers" not in config:
                    config["servers"] = {}
                
                config["servers"][server.name] = {
                    "command": server.command,
                    "args": server.args,
                    "env": server.env,
                    "enabled": True  
                }
                save_mcp_config(config)
                console.print(f"[green]✓ Server '{server.name}' added successfully[/green]\n")
                
                
                manager = get_mcp_manager()
                if manager.start_server(server.name, transport="stdio", command=server.command, args=server.args, env=server.env):
                    console.print(f"[green]✓ Server '{server.name}' started and connected[/green]\n")
                else:
                    console.print(f"[yellow]⚠ Server added but failed to connect. Use 'Test Connection' to retry.[/yellow]\n")
        
        elif action == "list":
            show_mcp_servers(config)
        
        elif action == "toggle":
            toggle_mcp_server(config)
        
        elif action == "remove":
            if not config.get("servers"):
                console.print("[yellow]No servers configured[/yellow]\n")
                continue
            
            server_names = list(config["servers"].keys())
            server_to_remove = select_with_arrows(
                {name: name for name in server_names},
                prompt_text="Select server to remove"
            )
            
            if server_to_remove and Confirm.ask(f"Remove server '{server_to_remove}'?"):
                
                manager = get_mcp_manager()
                manager.stop_server(server_to_remove)
                
                del config["servers"][server_to_remove]
                save_mcp_config(config)
                console.print(f"[green]✓ Server '{server_to_remove}' removed[/green]\n")
        
        elif action == "test":
            test_mcp_connection(config)


def toggle_mcp_server(config: Dict[str, Any]) -> None:
    
    servers = config.get("servers", {})
    
    if not servers:
        console.print("[yellow]No servers configured[/yellow]\n")
        return
    
    
    server_options = {}
    for name, server_config in servers.items():
        enabled = server_config.get("enabled", True)
        status = "🟢 ON" if enabled else "🔴 OFF"
        server_options[f"{name} ({status})"] = name
    
    selected = select_with_arrows(
        server_options,
        prompt_text="Select server to toggle"
    )
    
    if not selected:
        return
    
    server_name = server_options[selected]
    server_config = servers[server_name]
    current_status = server_config.get("enabled", True)
    
    
    new_status = not current_status
    server_config["enabled"] = new_status
    
    manager = get_mcp_manager()
    
    if new_status:
        
        console.print(f"\n[dim]Starting MCP server: {server_name}...[/dim]")
        
        spinner = Spinner("dots", text="[dim]Connecting to server...[/dim]", style="cyan")
        success = False
        
        with Live(spinner, refresh_per_second=10, transient=True):
            success = manager.start_server(
                server_name,
                transport="stdio",
                command=server_config.get("command", ""),
                args=server_config.get("args", []),
                env=server_config.get("env", {})
            )
        
        if success:
            save_mcp_config(config)
            console.print(f"[green]✓ Server '{server_name}' is now ON and connected[/green]\n")
        else:
            
            server_config["enabled"] = current_status
            console.print(f"[red]✗ Failed to start server '{server_name}'[/red]\n")
    else:
        
        console.print(f"\n[dim]Stopping MCP server: {server_name}...[/dim]")
        manager.stop_server(server_name)
        save_mcp_config(config)
        console.print(f"[yellow]✓ Server '{server_name}' is now OFF[/yellow]\n")


def show_mcp_servers(config: Dict[str, Any]) -> None:
    
    servers = config.get("servers", {})
    
    if not servers:
        console.print("[yellow]No MCP servers configured[/yellow]\n")
        return
    
    manager = get_mcp_manager()
    
    table = Table(title="Configured MCP Servers", border_style="cyan")
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Command", style="white")
    table.add_column("Args", style="dim")
    table.add_column("Enabled", style="white")
    table.add_column("Status", style="green")
    
    for name, server_config in servers.items():
        args_str = " ".join(server_config.get("args", []))
        enabled = server_config.get("enabled", True)
        enabled_str = "🟢 ON" if enabled else "🔴 OFF"
        
        is_connected = manager.is_connected(name)
        if enabled and is_connected:
            status = "✓ Connected"
            status_style = "green"
        elif enabled and not is_connected:
            status = "⚠ Disconnected"
            status_style = "yellow"
        else:
            status = "○ Stopped"
            status_style = "dim"
        
        table.add_row(
            name,
            server_config.get("command", ""),
            args_str or "—",
            enabled_str,
            f"[{status_style}]{status}[/{status_style}]"
        )
    
    console.print(table)
    console.print()


def test_mcp_connection(config: Dict[str, Any]) -> None:
    
    servers = config.get("servers", {})
    
    if not servers:
        console.print("[yellow]No servers to test[/yellow]\n")
        return
    
    server_names = list(servers.keys())
    server_to_test = select_with_arrows(
        {name: name for name in server_names},
        prompt_text="Select server to test"
    )
    
    if not server_to_test:
        return
    
    server_config = servers[server_to_test]
    manager = get_mcp_manager()
    
    
    manager.stop_server(server_to_test)
    
    command = server_config.get("command", "")
    console.print(f"\n[dim]Testing connection to '{server_to_test}'...[/dim]")
    if command == "npx":
        console.print("[dim]Note: First run may take longer as npx downloads the package[/dim]\n")
    
    spinner = Spinner("dots", text="[dim]Connecting to server...[/dim]", style="cyan")
    
    success = False
    error_message = None
    
    with Live(spinner, refresh_per_second=10, transient=True):
        try:
            success = manager.start_server(
                server_to_test,
                transport="stdio",
                command=command,
                args=server_config.get("args", []),
                env=server_config.get("env", {})
            )
        except Exception as e:
            error_message = str(e)
    
    if success:
        conn = manager.get_connection(server_to_test)
        console.print(Panel(
            f"[green]✓ Connection successful![/green]\n\n"
            f"Server is initialized and ready to use.\n"
            f"Capabilities: {list(conn.capabilities.keys()) if conn else 'Unknown'}",
            title=f"[bold green]Test Results: {server_to_test}[/bold green]",
            border_style="green",
            padding=(1, 2)
        ))
    else:
        error_details = []
        error_details.append("Could not establish connection to the MCP server.")
        error_details.append("\nPossible issues:")
        error_details.append("  • Command is incorrect")
        error_details.append("  • Server is not MCP-compatible")
        error_details.append("  • Missing dependencies")
        
        if error_message:
            error_details.append(f"\nError: {error_message}")
        
        console.print(Panel(
            "\n".join(error_details),
            title=f"[bold red]Test Results: {server_to_test}[/bold red]",
            border_style="red",
            padding=(1, 2)
        ))
    
    console.print()


def get_mcp_context_for_ai(config: Dict[str, Any]) -> str:
    
    try:
        manager = get_mcp_manager()
        
        
        all_resources = manager.get_all_resources()
        all_tools = manager.get_all_tools()
        
        if not all_resources and not all_tools:
            return ""
        
        context = "\n\n[Available MCP Tools - Use these automatically when needed]:\n"
        
        
        if all_tools:
            for server_name, tools in all_tools.items():
                context += f"\nFrom {server_name}:\n"
                for tool in tools:
                    tool_name = tool.get('name', 'Unknown')
                    tool_desc = tool.get('description', 'No description')
                    context += f"  • {tool_name}: {tool_desc}\n"
                    
                    
                    if 'inputSchema' in tool:
                        schema = tool['inputSchema']
                        if 'properties' in schema:
                            params = ', '.join(schema['properties'].keys())
                            context += f"    Parameters: {params}\n"
        
        
        if all_resources:
            context += "\nAvailable Resources:\n"
            for server_name, resources in all_resources.items():
                context += f"\nFrom {server_name}:\n"
                for resource in resources[:10]:
                    context += f"  • {resource.get('name', 'Unknown')}"
                    if resource.get('uri'):
                        context += f" ({resource['uri']})"
                    context += "\n"
        
        return context
        
    except Exception:
        return ""


def reset_mcp_config() -> None:
    
    shutdown_mcp_servers()
    MCP_CONFIG_PATH.unlink(missing_ok=True)
    console.print("[green]✓ MCP configuration reset[/green]\n")


def test_http_mcp_endpoint(url: str) -> Dict[str, Any]:
    
    import requests
    
    results = {
        "reachable": False,
        "mcp_compatible": False,
        "supports_resources": False,
        "supports_tools": False,
        "error": None
    }
    
    try:
        session = requests.Session()
        
        
        try:
            response = session.get(f"{url}/health", timeout=5)
            results["reachable"] = True
        except requests.exceptions.RequestException:
            
            results["reachable"] = True  
        
        
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "thoth-test",
                    "version": "0.1.0"
                }
            }
        }
        
        response = session.post(
            f"{url}/message",
            json=init_request,
            timeout=10,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 200:
            data = response.json()
            if "result" in data:
                results["mcp_compatible"] = True
                
                
                resources_request = {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "resources/list"
                }
                
                res_response = session.post(
                    f"{url}/message",
                    json=resources_request,
                    timeout=10,
                    headers={"Content-Type": "application/json"}
                )
                
                if res_response.status_code == 200:
                    res_data = res_response.json()
                    if "result" in res_data and "error" not in res_data:
                        results["supports_resources"] = True
                
                
                tools_request = {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/list"
                }
                
                tools_response = session.post(
                    f"{url}/message",
                    json=tools_request,
                    timeout=10,
                    headers={"Content-Type": "application/json"}
                )
                
                if tools_response.status_code == 200:
                    tools_data = tools_response.json()
                    if "result" in tools_data and "error" not in tools_data:
                        results["supports_tools"] = True
        
        session.close()
        
    except requests.exceptions.ConnectionError:
        results["error"] = "Connection refused - server not reachable"
    except requests.exceptions.Timeout:
        results["error"] = "Connection timeout"
    except Exception as e:
        results["error"] = str(e)
    
    return results


def quick_test_http_server() -> None:
    
    console.print("\n[bold cyan]🔍 Quick HTTP MCP Server Test[/bold cyan]\n")
    console.print("[dim]Test an HTTP endpoint without saving configuration[/dim]\n")
    
    url = prompt(HTML("<b>Server URL</b> (e.g., http://localhost:3000): ")).strip()
    
    if not url:
        console.print("[yellow]URL is required[/yellow]\n")
        return
    
    console.print(f"\n[dim]Testing {url}...[/dim]\n")
    
    spinner = Spinner("dots", text="[dim]Running tests...[/dim]", style="cyan")
    
    results = {}
    with Live(spinner, refresh_per_second=10, transient=True):
        results = test_http_mcp_endpoint(url)
    
    
    test_lines = []
    
    if results["error"]:
        test_lines.append(f"[red]✗ Error: {results['error']}[/red]")
    else:
        if results["reachable"]:
            test_lines.append("[green]✓ Server is reachable[/green]")
        else:
            test_lines.append("[red]✗ Server is not reachable[/red]")
        
        if results["mcp_compatible"]:
            test_lines.append("[green]✓ MCP protocol supported[/green]")
        else:
            test_lines.append("[red]✗ MCP protocol not supported[/red]")
        
        if results["supports_resources"]:
            test_lines.append("[green]✓ Resources endpoint available[/green]")
        else:
            test_lines.append("[yellow]⚠ Resources endpoint not available[/yellow]")
        
        if results["supports_tools"]:
            test_lines.append("[green]✓ Tools endpoint available[/green]")
        else:
            test_lines.append("[yellow]⚠ Tools endpoint not available[/yellow]")
    
    console.print(Panel(
        "\n".join(test_lines),
        title="[bold cyan]HTTP MCP Test Results[/bold cyan]",
        border_style="cyan",
        padding=(1, 2)
    ))
    
    if results["mcp_compatible"] and not results["error"]:
        if Confirm.ask("\n[bold]Add this server to your configuration?[/bold]"):
            name = prompt(HTML("<b>Server name</b>: ")).strip()
            if name:
                config = load_mcp_config()
                if "servers" not in config:
                    config["servers"] = {}
                
                config["servers"][name] = {
                    "command": "__http__",
                    "args": [url],
                    "env": {}
                }
                save_mcp_config(config)
                console.print(f"[green]✓ Server '{name}' added successfully[/green]\n")
    
    console.print()