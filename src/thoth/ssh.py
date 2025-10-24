

import json
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from .display import console, select_with_arrows
from .crypto import encrypt_value, decrypt_value

SSH_CONFIG_PATH = Path.home() / ".thoth_ssh_config.json"


def load_ssh_config() -> Dict[str, Any]:
    
    if not SSH_CONFIG_PATH.exists():
        return {}
    
    try:
        data = json.loads(SSH_CONFIG_PATH.read_text(encoding="utf-8"))
        
        if data.get("password") and data["password"].startswith("encrypted:"):
            data["password"] = decrypt_value(data["password"][10:])
        if data.get("private_key_path"):
            
            data["private_key_path"] = str(Path(data["private_key_path"]).expanduser())
        return data
    except Exception as e:
        console.print(f"[red]Error loading SSH config: {e}[/red]")
        return {}


def save_ssh_config(config: Dict[str, Any]) -> None:
    
    config_copy = config.copy()
    
    
    if config_copy.get("password"):
        config_copy["password"] = f"encrypted:{encrypt_value(config_copy['password'])}"
    
    SSH_CONFIG_PATH.write_text(json.dumps(config_copy, indent=2), encoding="utf-8")
    SSH_CONFIG_PATH.chmod(0o600)


def run_ssh_command(
    host: str,
    command: str,
    user: Optional[str] = None,
    password: Optional[str] = None,
    private_key_path: Optional[str] = None,
    port: int = 22,
    timeout: int = 30
) -> Optional[Dict[str, Any]]:
    """
    Execute a command on a remote host via SSH.
    
    Args:
        host: Remote host IP or hostname
        command: Command to execute
        user: SSH username (from config if not provided)
        password: SSH password (from config if not provided)
        private_key_path: Path to private key file (from config if not provided)
        port: SSH port (default: 22)
        timeout: Command timeout in seconds
    
    Returns:
        Dict with stdout, stderr, and return_code, or None if failed
    """
    
    config = load_ssh_config()
    
    
    if user is None:
        user = config.get("default_user", "")
    if password is None:
        password = config.get("password")
    if private_key_path is None:
        private_key_path = config.get("private_key_path")
    
    if not user:
        return {
            "stdout": "",
            "stderr": "No SSH user configured. Use /ssh to configure.",
            "return_code": -1,
            "success": False
        }
    
    try:
        
        ssh_cmd = ["ssh"]
        
        
        if port != 22:
            ssh_cmd.extend(["-p", str(port)])
        
        
        if private_key_path and Path(private_key_path).exists():
            ssh_cmd.extend(["-i", private_key_path])
        
        
        ssh_cmd.extend([
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "LogLevel=ERROR",
            "-o", "ConnectTimeout=10"
        ])
        
        
        ssh_cmd.append(f"{user}@{host}")
        
        
        ssh_cmd.append(command)
        
        
        if password:
            
            ssh_cmd = ["sshpass", "-p", password] + ssh_cmd
        
        result = subprocess.run(
            ssh_cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "return_code": result.returncode,
            "success": result.returncode == 0
        }
    
    except subprocess.TimeoutExpired:
        return {
            "stdout": "",
            "stderr": "Command timed out",
            "return_code": -1,
            "success": False
        }
    except FileNotFoundError as e:
        if "sshpass" in str(e):
            return {
                "stdout": "",
                "stderr": "sshpass not found. Install it for password authentication: brew install sshpass (macOS) or apt-get install sshpass (Linux)",
                "return_code": -1,
                "success": False
            }
        return {
            "stdout": "",
            "stderr": f"SSH command failed: {str(e)}",
            "return_code": -1,
            "success": False
        }
    except Exception as e:
        return {
            "stdout": "",
            "stderr": f"Error: {str(e)}",
            "return_code": -1,
            "success": False
        }


def configure_ssh_interactive() -> None:
    
    config = load_ssh_config()
    
    console.print("\n[bold cyan]🔐 SSH Configuration[/bold cyan]\n")
    console.print("[dim]Configure default SSH credentials for GCP VMs[/dim]\n")
    
    
    if config.get("default_user"):
        show_ssh_config()
    
    
    menu_options = {
        "Configure SSH Credentials": "configure",
        "View Current Configuration": "view",
        "Test SSH Connection": "test",
        "Reset Configuration": "reset",
        "Back": "back"
    }
    
    choice = select_with_arrows(menu_options, prompt_text="SSH Configuration Menu")
    
    if not choice or choice == "Back":
        return
    
    action = menu_options[choice]
    
    if action == "view":
        show_ssh_config()
        return
    
    elif action == "test":
        test_ssh_connection()
        return
    
    elif action == "reset":
        if Confirm.ask("Reset SSH configuration?"):
            reset_ssh_config()
        return
    
    elif action == "configure":
        
        current_user = config.get("default_user", "")
        
        if current_user:
            console.print(f"\n[dim]Current user: {current_user}[/dim]")
            use_current = Confirm.ask("Keep current username?", default=True)
            if use_current:
                username = current_user
            else:
                username = console.input("[bold]Default SSH username:[/bold] ").strip()
        else:
            username = console.input("[bold]Default SSH username:[/bold] ").strip()
        
        if not username:
            console.print("[yellow]Username is required[/yellow]\n")
            return
        
        
        auth_methods = {
            "SSH Key (recommended)": "key",
            "Password": "password"
        }
        
        auth_choice = select_with_arrows(
            auth_methods,
            prompt_text="Select authentication method"
        )
        
        if not auth_choice:
            console.print("[yellow]Authentication method is required[/yellow]\n")
            return
        
        auth_method = auth_methods[auth_choice]
        
        password = None
        private_key_path = None
        
        if auth_method == "password":
            import getpass
            password = getpass.getpass("Password: ").strip()
            if not password:
                console.print("[yellow]Password is required[/yellow]\n")
                return
        else:
            default_key = config.get("private_key_path", str(Path.home() / ".ssh" / "id_rsa"))
            console.print(f"\n[dim]Default: {default_key}[/dim]")
            
            key_input = console.input("[bold]Private key path (press Enter for default):[/bold] ").strip()
            private_key_path = key_input if key_input else default_key
            
            
            private_key_path = str(Path(private_key_path).expanduser())
            
            if not Path(private_key_path).exists():
                console.print(f"[yellow]Private key not found: {private_key_path}[/yellow]\n")
                return
        
        
        new_config = {
            "default_user": username,
            "auth_method": auth_method,
            "password": password if auth_method == "password" else None,
            "private_key_path": private_key_path if auth_method == "key" else None
        }
        
        save_ssh_config(new_config)
        console.print(f"\n[green]✓ SSH configuration saved[/green]")
        console.print(f"[dim]User: {username}[/dim]")
        console.print(f"[dim]Auth: {auth_method}[/dim]\n")


def show_ssh_config() -> None:
    
    config = load_ssh_config()
    
    if not config:
        console.print("[yellow]No SSH configuration set[/yellow]")
        console.print("[dim]Use /ssh to configure default SSH credentials[/dim]\n")
        return
    
    table = Table(title="SSH Configuration", border_style="cyan")
    table.add_column("Setting", style="cyan", no_wrap=True)
    table.add_column("Value", style="white")
    
    table.add_row("Default User", config.get("default_user", "[dim]Not set[/dim]"))
    
    auth_method = config.get("auth_method", "")
    if auth_method == "key":
        table.add_row("Auth Method", "🔑 SSH Key")
        table.add_row("Private Key", config.get("private_key_path", "[dim]Not set[/dim]"))
    elif auth_method == "password":
        table.add_row("Auth Method", "🔒 Password")
        table.add_row("Password", "[green]✓ Configured[/green]")
    
    console.print(table)
    console.print()


def get_ssh_context_for_ai() -> str:
    
    from .utils import load_system_prompt_from_md
    
    config = load_ssh_config()
    
    if not config or not config.get("default_user"):
        return ""
    
    
    try:
        ssh_context_base = load_system_prompt_from_md("./prompts/ssh_context.md")
    except (FileNotFoundError, ValueError):
        ssh_context_base = ""
    
    context = "\n\n" + "="*80 + "\n"
    context += "SSH REMOTE EXECUTION AVAILABLE\n"
    context += "="*80 + "\n\n"
    
    context += "SSH Configuration:\n"
    context += f"  • Default User: {config.get('default_user')}\n"
    context += f"  • Auth Method: {config.get('auth_method', 'key')}\n"
    
    if config.get("auth_method") == "key":
        context += f"  • Private Key: {config.get('private_key_path')}\n"
    
    context += "\n"
    context += ssh_context_base
    context += "\n" + "="*80 + "\n"
    
    return context


def reset_ssh_config() -> None:
    
    SSH_CONFIG_PATH.unlink(missing_ok=True)
    console.print("[green]✓ SSH configuration reset[/green]\n")


def test_ssh_connection() -> None:
    
    from .gcp import load_gcp_config, run_gcloud_command
    
    config = load_ssh_config()
    
    if not config.get("default_user"):
        console.print("[yellow]No SSH configuration found. Please configure SSH first.[/yellow]\n")
        return
    
    gcp_config = load_gcp_config()
    
    if not gcp_config.get("project_id"):
        console.print("[yellow]No GCP project configured. Please configure GCP first.[/yellow]\n")
        return
    
    console.print("\n[dim]Fetching running VMs...[/dim]\n")
    
    
    output = run_gcloud_command(
        ["compute", "instances", "list", "--filter=status=RUNNING", "--format=json"],
        project_id=gcp_config.get("project_id")
    )
    
    if not output:
        console.print("[yellow]No running VMs found[/yellow]\n")
        return
    
    try:
        vms = json.loads(output)
        
        if not vms:
            console.print("[yellow]No running VMs found[/yellow]\n")
            return
        
        
        vm_options = {}
        for vm in vms:
            vm_name = vm.get("name", "")
            zone = vm.get("zone", "").split("/")[-1]
            
            
            internal_ip = ""
            for interface in vm.get("networkInterfaces", []):
                if interface.get("networkIP"):
                    internal_ip = interface["networkIP"]
                    break
            
            vm_options[f"{vm_name} ({zone}) - {internal_ip}"] = {
                "name": vm_name,
                "zone": zone,
                "ip": internal_ip
            }
        
        selected = select_with_arrows(
            {k: k for k in vm_options.keys()},
            prompt_text="Select VM to test SSH connection"
        )
        
        if not selected:
            return
        
        vm_info = vm_options[selected]
        
        console.print(f"\n[dim]Testing SSH connection to {vm_info['name']} ({vm_info['ip']})...[/dim]\n")
        
        result = run_ssh_command(
            host=vm_info['ip'],
            command="echo 'SSH connection successful' && uname -a",
            timeout=10
        )
        
        if result and result["success"]:
            console.print(Panel(
                f"[green]✓ SSH connection successful![/green]\n\n"
                f"VM: {vm_info['name']}\n"
                f"IP: {vm_info['ip']}\n"
                f"Zone: {vm_info['zone']}\n\n"
                f"System info:\n{result['stdout']}",
                title=f"[bold green]SSH Test Results[/bold green]",
                border_style="green",
                padding=(1, 2)
            ))
        else:
            error_msg = result["stderr"] if result else "Unknown error"
            console.print(Panel(
                f"[red]✗ SSH connection failed[/red]\n\n"
                f"VM: {vm_info['name']}\n"
                f"IP: {vm_info['ip']}\n"
                f"Zone: {vm_info['zone']}\n\n"
                f"Error: {error_msg}",
                title=f"[bold red]SSH Test Results[/bold red]",
                border_style="red",
                padding=(1, 2)
            ))
        
        console.print()
        
    except json.JSONDecodeError:
        console.print("[red]Error parsing VM list[/red]\n")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]\n")