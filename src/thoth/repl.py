"""REPL implementation for interactive chat."""

import json
import subprocess
import atexit
import re
from pathlib import Path
from threading import Thread
from typing import Optional, Dict
import typer
from openai import OpenAI
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.formatted_text import HTML, FormattedText
from prompt_toolkit.styles import Style
from rich.align import Align
from rich.live import Live
from rich.panel import Panel
from rich.spinner import Spinner
from rich.syntax import Syntax
from rich.text import Text
from .config import reset_config, load_config, save_config
from .display import console, select_with_arrows, select_model_interactive
from .models import choose_provider_and_model, fetch_openai_models, fetch_openrouter_models, PROVIDERS
from .utils import load_system_prompt_from_md
from .mcp import (
    configure_mcp_interactive,
    load_mcp_config,
    get_mcp_context_for_ai,
    initialize_mcp_servers,
    shutdown_mcp_servers,
    get_mcp_manager
)
from .gcp import (
    configure_gcp_interactive,
    get_gcp_context_for_ai
)
from .infrastructure import (
    analyze_infrastructure_interactive,
    view_stored_knowledge_interactive,
    get_infrastructure_context_for_ai
)
from .ssh import (
    configure_ssh_interactive,
    get_ssh_context_for_ai,
    run_ssh_command,
    load_ssh_config
)


def process_file_mentions(message: str) -> str:
    """
    Process @file mentions in the message and include file contents.
    
    Supports:
    - @filename.txt
    - @./path/to/file.py
    - @/absolute/path/file.json
    """
    # Find all @file mentions
    pattern = r'@([\w\-./]+\.\w+)'
    matches = re.findall(pattern, message)
    
    if not matches:
        return message
    
    enhanced_message = message
    file_contents = []
    
    for file_path in matches:
        try:
            # Resolve path
            path = Path(file_path).expanduser()
            
            # Try relative to current directory if not absolute
            if not path.is_absolute():
                path = Path.cwd() / file_path
            
            if not path.exists():
                file_contents.append(f"\n[File: {file_path}]\n⚠️  File not found: {path}\n")
                console.print(f"[yellow]⚠️  File not found: {file_path}[/yellow]")
                continue
            
            # Check file size (limit to 100KB)
            if path.stat().st_size > 100_000:
                file_contents.append(f"\n[File: {file_path}]\n⚠️  File too large (>100KB). Please use a smaller file.\n")
                console.print(f"[yellow]⚠️  File too large: {file_path} (>100KB)[/yellow]")
                continue
            
            # Read file content
            try:
                content = path.read_text(encoding='utf-8')
                file_contents.append(f"\n[File: {file_path}]\n```\n{content}\n```\n")
                console.print(f"[dim]📄 Reading file: {file_path}[/dim]")
            except UnicodeDecodeError:
                # Binary file
                file_contents.append(f"\n[File: {file_path}]\n⚠️  Binary file detected. Cannot display content.\n")
                console.print(f"[yellow]⚠️  Binary file: {file_path}[/yellow]")
        
        except Exception as e:
            file_contents.append(f"\n[File: {file_path}]\n⚠️  Error reading file: {str(e)}\n")
            console.print(f"[yellow]⚠️  Error reading {file_path}: {str(e)}[/yellow]")
    
    # Append all file contents to the message
    if file_contents:
        enhanced_message += "\n\n" + "="*80 + "\n"
        enhanced_message += "ATTACHED FILES\n"
        enhanced_message += "="*80
        enhanced_message += "".join(file_contents)
    
    return enhanced_message


class SlashCompleter(Completer):
    """Beautiful auto-completer for slash commands with rich formatting."""
    
    def __init__(self, commands: Dict[str, str]):
        """
        Initialize completer with commands.
        
        Args:
            commands: Dict mapping command names to descriptions
        """
        self.commands = commands

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor.lstrip()
        
        # Only complete if starts with /
        if not text.startswith("/"):
            return
        
        # Get the partial command (without the /)
        partial = text[1:].lower()
        
        # Find matching commands
        for cmd_name, cmd_desc in self.commands.items():
            cmd_lower = cmd_name.lower()
            
            # Match if command starts with partial input
            if cmd_lower.startswith(partial):
                # Create formatted display with icon
                icon = self._get_command_icon(cmd_name)
                
                # Format: /command — description
                display = FormattedText([
                    ('class:command-slash', '/'),
                    ('class:command-name', cmd_name),
                    ('class:command-separator', ' — '),
                    ('class:command-desc', cmd_desc),
                ])
                
                yield Completion(
                    text=cmd_name,
                    start_position=-len(text) + 1,  # +1 to keep the /
                    display=display,
                )
    
    def _get_command_icon(self, cmd_name: str) -> str:
        """Get emoji icon for command."""
        icons = {
            "help": "📖",
            "provider": "🔄",
            "model": "🤖",
            "clear": "🧹",
            "reset": "♻️",
            "mcp": "🔌",
            "gcp": "☁️",
            "ssh": "🔐",
            "analyze": "🔍",
            "knowledge": "📚",
            "exit": "👋"
        }
        return icons.get(cmd_name, "•")


# Custom style for the completer - darker theme
completer_style = Style.from_dict({
    # Completion menu background and text
    'completion-menu.completion': 'bg:#1a1a1a #c0c0c0',  # Darker background, lighter text
    'completion-menu.completion.current': 'bg:#C2A14A #0a0a0a bold',  # Gold highlight with very dark text
    'completion-menu.meta.completion': 'bg:#1a1a1a #909090',  # Darker gray for meta
    'completion-menu.meta.completion.current': 'bg:#C2A14A #0a0a0a',  # Gold highlight for current meta
    'scrollbar.background': 'bg:#1a1a1a',  # Darker scrollbar background
    'scrollbar.button': 'bg:#C2A14A',  # Gold scrollbar button
    
    # Custom classes for our formatted text
    'command-slash': '#C2A14A bold',  # Gold slash
    'command-name': '#6FA8DC bold',  # Softer blue for command name
    'command-separator': '#707070',  # Darker gray separator
    'command-desc': '#b0b0b0',  # Medium gray for description
})


def show_session_banner(provider: str, model: str) -> None:
    """Display the session banner with current provider and model."""
    console.print(Align.center(Panel(
        f"[bold #B8860B]Thoth AI Interactive Shell[/bold #B8860B] — "
        f"[#4682B4]{provider}[/#4682B4] • [#4682B4]{model}[/#4682B4]\n"
        "[dim]Chat with AI • Run shell commands with ` • Type /help for commands[/dim]",
        border_style="gold1",
        expand=False
    )))


def run_repl(client: OpenAI, provider: str, model: str) -> None:

    show_session_banner(provider, model)
    
    console.print("[dim]Initializing MCP servers...[/dim]")
    initialize_mcp_servers()
    
    atexit.register(shutdown_mcp_servers)

    slash_commands = {
        "help": "Show available commands and usage",
        "provider": "Switch AI provider (OpenAI ↔ OpenRouter)",
        "model": "Change the current AI model",
        "clear": "Clear conversation history",
        "reset": "Reset all settings and configuration",
        "mcp": "Manage MCP servers (add, list, remove, test)",
        "gcp": "Configure GCP settings (project, region, zone)",
        "ssh": "Configure SSH hosts for remote command execution",
        "analyze": "Analyze infrastructure and store knowledge",
        "knowledge": "View stored infrastructure knowledge",
        "exit": "Quit Thoth CLI"
    }
    
    session = PromptSession(
        completer=SlashCompleter(slash_commands),
        style=completer_style,
        complete_while_typing=True,
        complete_in_thread=True
    )

    try:
        system_prompt_text = load_system_prompt_from_md("./prompts/prompt.md")
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    except ValueError as e:
        console.print(f"[yellow]{e}[/yellow]")
        raise typer.Exit(1)

    system_prompt = {"role": "system", "content": system_prompt_text}
    chat_history: list[dict] = [system_prompt]
    
    # Load MCP config for AI context
    mcp_config = load_mcp_config()

    while True:
        try:
            # Single unified prompt
            prompt_symbol = HTML('<ansiyellow><b>thoth</b></ansiyellow> &gt; ')
            
            # Get user input
            user_input = session.prompt(prompt_symbol).strip()

            if not user_input:
                continue

            # Shell Command Mode (starts with `)
            if user_input.startswith("`"):
                shell_cmd = user_input[1:].strip()
                
                if not shell_cmd:
                    console.print("[yellow]Usage: `<command>  (e.g., `ls -la)[/yellow]")
                    continue
                
                try:
                    result = subprocess.run(
                        shell_cmd, 
                        shell=True, 
                        capture_output=True, 
                        text=True,
                        timeout=30
                    )
                    
                    # Display output
                    if result.stdout:
                        console.print(Panel(
                            result.stdout.rstrip(),
                            title="[cyan]Shell[/cyan]",
                            border_style="cyan",
                            padding=(0, 1)
                        ))
                    
                    if result.stderr:
                        syntax = Syntax(result.stderr.rstrip(), "python", theme="monokai", line_numbers=False)
                        console.print(Panel(
                            syntax,
                            title="[red]Error[/red]",
                            border_style="red",
                            padding=(0, 1)
                        ))
                    
                    if not result.stdout and not result.stderr:
                        console.print("[dim]✓ Command executed successfully[/dim]\n")
                    
                    if result.returncode != 0:
                        console.print(f"[dim red]Exit code: {result.returncode}[/dim red]\n")
                    
                except subprocess.TimeoutExpired:
                    console.print(Panel(
                        "[red]⏱️  Command timed out after 30 seconds[/red]",
                        border_style="red"
                    ))
                except Exception as e:
                    console.print(Panel(
                        f"[red]Error:[/red] {str(e)}",
                        border_style="red",
                        padding=(1, 2)
                    ))
                continue

            # Slash Commands
            if user_input.startswith("/"):
                cmd = user_input[1:].strip().split(maxsplit=1)[0].lower()

                if cmd == "help":
                    console.print(Panel(
                        "[bold cyan]💬 Chat Commands[/bold cyan]\n\n"
                        "[bold]/help[/bold] — show this help menu\n"
                        "[bold]/provider[/bold] — switch AI provider (OpenAI ↔ OpenRouter)\n"
                        "[bold]/model[/bold] — change AI model\n"
                        "[bold]/clear[/bold] — clear conversation history\n"
                        "[bold]/reset[/bold] — reset all settings and start fresh\n"
                        "[bold]/exit[/bold] — quit Thoth\n\n"
                        "[bold cyan]🔌 MCP Commands[/bold cyan]\n\n"
                        "[bold]/mcp[/bold] — manage MCP servers (add, list, remove, test)\n\n"
                        "[bold cyan]☁️  Cloud Platform Commands[/bold cyan]\n\n"
                        "[bold]/gcp[/bold] — configure GCP settings (project, region, zone)\n"
                        "[bold]/analyze[/bold] — analyze infrastructure and store knowledge\n"
                        "[bold]/knowledge[/bold] — view stored infrastructure knowledge\n\n"
                        "[bold cyan]🔐 Remote Access Commands[/bold cyan]\n\n"
                        "[bold]/ssh[/bold] — configure SSH hosts for remote command execution\n\n"
                        "[bold cyan]🖥️  Shell Commands[/bold cyan]\n\n"
                        "[bold]`<command>[/bold] — run local shell command\n"
                        "  Examples: `ls -la, `git status, `pwd\n\n"
                        "[bold cyan]📄 File Mentions[/bold cyan]\n\n"
                        "[bold]@filename[/bold] — mention a file to include its content\n"
                        "  Examples: @config.yaml, @./src/main.py, @/etc/hosts\n"
                        "  Supports: .txt, .py, .js, .json, .yaml, .md, etc.\n"
                        "  Max size: 100KB per file\n\n"
                        "[bold cyan]🤖 AI Capabilities[/bold cyan]\n\n"
                        "Chat naturally with AI and get intelligent responses.\n"
                        "MCP servers provide real-time context and capabilities.",
                        title="📜 Thoth Commands",
                        border_style="#B8860B",
                        padding=(1, 2)
                    ))
                
                elif cmd == "mcp":
                    configure_mcp_interactive()
                    mcp_config = load_mcp_config()
                
                elif cmd == "gcp":
                    configure_gcp_interactive()
                
                elif cmd == "analyze":
                    analyze_infrastructure_interactive()
                
                elif cmd == "knowledge":
                    view_stored_knowledge_interactive()

                elif cmd == "ssh":
                    configure_ssh_interactive()
                
                elif cmd == "provider":
                    console.print("[cyan]🔄 Switching AI provider...[/cyan]\n")
                    
                    # Select new provider
                    new_provider = select_with_arrows(
                        PROVIDERS,
                        prompt_text="Select AI Provider"
                    )
                    
                    if not new_provider:
                        console.print("[yellow]Provider change cancelled[/yellow]\n")
                        continue
                    
                    # Get API key
                    from rich.prompt import Prompt
                    api_key = Prompt.ask(
                        f"[bold]Enter your {new_provider} API key[/bold]",
                        password=True
                    ).strip()
                    
                    if not api_key:
                        console.print("[yellow]No API key provided. Cancelled.[/yellow]\n")
                        continue
                    
                    # Fetch models dynamically
                    console.print(f"[dim]Fetching available models from {new_provider}...[/dim]")
                    
                    if new_provider == "OpenAI":
                        model_list = fetch_openai_models(api_key)
                    else:  # OpenRouter
                        model_list = fetch_openrouter_models(api_key)
                    
                    if not model_list:
                        console.print(f"[red]No models available from {new_provider}. Cancelled.[/red]\n")
                        continue
                    
                    console.print(f"[green]✓ Found {len(model_list)} models[/green]\n")
                    
                    new_model = select_model_interactive(model_list)
                    
                    if not new_model:
                        console.print("[yellow]Model selection cancelled[/yellow]\n")
                        continue
                    
                    # Create new client
                    if new_provider == "OpenAI":
                        client = OpenAI(api_key=api_key)
                    else:  # OpenRouter
                        client = OpenAI(
                            api_key=api_key,
                            base_url="https://openrouter.ai/api/v1"
                        )
                    
                    # Update variables
                    provider = new_provider
                    model = new_model
                    
                    # Save configuration
                    save_config(provider, api_key, model)
                    console.print(f"[green]✓ Switched to {provider} • {model}[/green]\n")
                    
                    # Show updated banner
                    show_session_banner(provider, model)
                    
                    # Reset chat history
                    chat_history = [system_prompt]
                
                elif cmd == "model":
                    console.print("[cyan]🔄 Changing AI model...[/cyan]\n")
                    
                    # Get current config
                    config = load_config()
                    api_key = config.get("api_key", "")
                    
                    if not api_key:
                        console.print("[red]No API key found. Please use /provider first.[/red]\n")
                        continue
                    
                    # Fetch models dynamically
                    console.print(f"[dim]Fetching available models from {provider}...[/dim]")
                    
                    if provider == "OpenAI":
                        model_list = fetch_openai_models(api_key)
                    else:  # OpenRouter
                        model_list = fetch_openrouter_models(api_key)
                    
                    if not model_list:
                        console.print(f"[red]No models available from {provider}. Cancelled.[/red]\n")
                        continue
                    
                    console.print(f"[green]✓ Found {len(model_list)} models[/green]\n")
                    
                    new_model = select_model_interactive(model_list)
                    
                    if not new_model:
                        console.print("[yellow]Model change cancelled[/yellow]\n")
                        continue
                    
                    # Update model
                    model = new_model
                    
                    # Save configuration with existing API key
                    save_config(provider, api_key, model)
                    console.print(f"[green]✓ Model changed to {model}[/green]\n")
                    
                    # Show updated banner
                    show_session_banner(provider, model)
                    
                    # Reset chat history
                    chat_history = [system_prompt]
                
                elif cmd == "clear":
                    chat_history = [system_prompt]
                    console.print("[green]✓ Conversation history cleared[/green]\n")
                
                elif cmd == "reset":
                    console.print("[yellow]🔄 Resetting all configuration...[/yellow]\n")
                    reset_config()
                    console.print("[green]✓ Configuration reset[/green]\n")
                    new_client, new_provider, new_model = choose_provider_and_model(reset=False)
                    client = new_client
                    provider = new_provider
                    model = new_model
                    
                    # Show updated banner
                    show_session_banner(provider, model)
                    
                    # Reset chat history
                    chat_history = [system_prompt]
                
                elif cmd == "exit":
                    console.print("[bold #B8860B]Until the stars speak again.[/bold #B8860B]")
                    shutdown_mcp_servers()
                    break
                else:
                    console.print(f"[yellow]Unknown command: {user_input}[/yellow]")
                    console.print("[dim]Type /help to see available commands[/dim]")
                continue

            # Normal AI Chat Message - Process @file mentions FIRST
            enhanced_message = process_file_mentions(user_input)

            # Add MCP context
            if mcp_config.get("servers"):
                try:
                    mcp_context = get_mcp_context_for_ai(mcp_config)
                    if mcp_context:
                        enhanced_message += mcp_context
                except Exception as e:
                    console.print(f"[yellow]Error getting MCP context: {e}[/yellow]")

            # Add GCP context
            try:
                gcp_context = get_gcp_context_for_ai()
                if gcp_context:
                    enhanced_message += gcp_context
            except Exception as e:
                console.print(f"[yellow]Error getting GCP context: {e}[/yellow]")

            # Add SSH context
            try:
                ssh_context = get_ssh_context_for_ai()
                if ssh_context:
                    enhanced_message += ssh_context
            except Exception as e:
                console.print(f"[yellow]Error getting SSH context: {e}[/yellow]")

            # Add Infrastructure context
            try:
                from .gcp import load_gcp_config
                from .infrastructure import has_stored_knowledge
                
                gcp_config_data = load_gcp_config()
                if gcp_config_data.get("project_id"):
                    # Show notification that we're loading knowledge
                    if has_stored_knowledge(gcp_config_data["project_id"]):
                        console.print("[dim]📚 Loading infrastructure knowledge...[/dim]")
                    
                    infra_context = get_infrastructure_context_for_ai(gcp_config_data["project_id"])
                    if infra_context:
                        enhanced_message += infra_context
                        # Show what knowledge was loaded
                        console.print("[dim]✓ Knowledge loaded: VMs, Networks, Firewall Rules, Load Balancers[/dim]\n")
            except Exception as e:
                console.print(f"[yellow]Error getting infrastructure context: {e}[/yellow]")
            
            chat_history.append({"role": "user", "content": enhanced_message})
            
            spinner = Spinner("circle", text="[dim]Wisdom stirs within me...[/dim]", style="#B8860B")
            response_container = {}

            def fetch_ai_response():
                try:
                    # Get MCP manager and available tools
                    manager = get_mcp_manager()
                    all_tools = manager.get_all_tools()
                    
                    # Convert MCP tools to OpenAI tools format
                    tools = []
                    if all_tools:
                        for server_name, server_tools in all_tools.items():
                            for tool in server_tools:
                                tools.append({
                                    "type": "function",
                                    "function": {
                                        "name": f"{server_name}_{tool['name']}",
                                        "description": tool.get('description', ''),
                                        "parameters": tool.get('inputSchema', {"type": "object", "properties": {}})
                                    }
                                })
                    
                    # Add GCP command execution function
                    from .gcp import load_gcp_config
                    gcp_config = load_gcp_config()
                    
                    if gcp_config.get("project_id"):
                        tools.append({
                            "type": "function",
                            "function": {
                                "name": "gcp_execute_command",
                                "description": "Execute a gcloud command and return the output. Use this to fetch GCP resource information.",
                                "parameters": {
                                    "type": "object",
                                    "properties": {
                                        "args": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                            "description": "List of gcloud command arguments (e.g., ['compute', 'instances', 'list'])"
                                        },
                                        "format": {
                                            "type": "string",
                                            "description": "Output format (e.g., 'json', 'table', 'yaml'). Default is 'json'.",
                                            "default": "json"
                                        }
                                    },
                                    "required": ["args"]
                                }
                            }
                        })
                        
                        # Add Infrastructure Knowledge Update function
                        tools.append({
                            "type": "function",
                            "function": {
                                "name": "update_infrastructure_knowledge",
                                "description": "Update the infrastructure knowledge base by re-analyzing GCP resources. Use this when the user asks to update, refresh, or re-analyze infrastructure knowledge.",
                                "parameters": {
                                    "type": "object",
                                    "properties": {},
                                    "required": []
                                }
                            }
                        })

                    # Add SSH command execution function
                    ssh_config = load_ssh_config()

                    if ssh_config.get("default_user"):
                        tools.append({
                            "type": "function",
                            "function": {
                                "name": "ssh_execute_command",
                                "description": "Execute a command on a GCP VM via SSH. First get the VM's IP using gcp_execute_command, then use this function to run commands on that VM.",
                                "parameters": {
                                    "type": "object",
                                    "properties": {
                                        "host": {
                                            "type": "string",
                                            "description": "The VM's IP address (internal or external IP from GCP)"
                                        },
                                        "command": {
                                            "type": "string",
                                            "description": "Command to execute on the remote VM"
                                        }
                                    },
                                    "required": ["host", "command"]
                                }
                            }
                        })
                    
                    # Make initial API call with tools
                    try:
                        if tools:
                            response = client.chat.completions.create(
                                model=model,
                                messages=chat_history,
                                tools=tools,
                                tool_choice="auto",
                                timeout=60.0  # Add timeout
                            )
                        else:
                            response = client.chat.completions.create(
                                model=model,
                                messages=chat_history,
                                timeout=60.0  # Add timeout
                            )
                    except json.JSONDecodeError as e:
                        # Handle JSON decode errors specifically
                        response_container["error"] = f"API response parsing error: {str(e)}\n\nThis usually means:\n1. The response was too large\n2. Network connection was interrupted\n3. API returned an error\n\nTry:\n- Simplifying your question\n- Checking your internet connection\n- Trying again in a moment"
                        return
                    except Exception as e:
                        response_container["error"] = f"API request failed: {str(e)}"
                        return
                    
                    message = response.choices[0].message
                    
                    # Handle tool calling loop
                    max_iterations = 5
                    iteration = 0
                    
                    while hasattr(message, 'tool_calls') and message.tool_calls and iteration < max_iterations:
                        iteration += 1
                        
                        # Process each tool call
                        tool_call = message.tool_calls[0]
                        function_name = tool_call.function.name
                        
                        # Parse arguments safely
                        try:
                            function_args = json.loads(tool_call.function.arguments) if tool_call.function.arguments else {}
                        except json.JSONDecodeError:
                            console.print(f"[yellow]Warning: Invalid JSON arguments for {function_name}[/yellow]")
                            function_args = {}
                        
                        # Execute the tool
                        tool_result = None

                        if function_name == "gcp_execute_command":
                            # Execute GCP command directly
                            from .gcp import run_gcloud_command
                            from .infrastructure import auto_refresh_knowledge
                            
                            args = function_args.get("args", [])
                            output_format = function_args.get("format", "json")
                            
                            # Add format flag if not already present
                            if output_format and not any("--format" in arg for arg in args):
                                args.append(f"--format={output_format}")
                            
                            console.print(f"\n[dim]⚙️ [#4682B4]gcloud {' '.join(args)}[/#4682B4][/dim]")
                            
                            output = run_gcloud_command(args, project_id=gcp_config.get("project_id"))
                            
                            if output:
                                # Truncate very large outputs to prevent JSON parsing issues
                                max_output_size = 50000  # 50KB limit
                                if len(output) > max_output_size:
                                    output = output[:max_output_size] + "\n\n[Output truncated - too large]"
                                
                                tool_result = {
                                    "success": True,
                                    "output": output,
                                    "command": f"gcloud {' '.join(args)}"
                                }
                                
                                # Auto-refresh knowledge if this was a modification command
                                modification_commands = [
                                    "create", "delete", "update", "add", "remove", 
                                    "start", "stop", "reset", "set-machine-type",
                                    "attach-disk", "detach-disk", "add-tags", "remove-tags"
                                ]
                                
                                if any(cmd in args for cmd in modification_commands):
                                    # Check if knowledge exists before refreshing
                                    from .infrastructure import has_stored_knowledge
                                    if has_stored_knowledge(gcp_config.get("project_id")):
                                        auto_refresh_knowledge(gcp_config.get("project_id"))
                            else:
                                tool_result = {
                                    "success": False,
                                    "error": "Command failed or returned no output",
                                    "command": f"gcloud {' '.join(args)}"
                                }

                        elif function_name == "update_infrastructure_knowledge":
                            # Update infrastructure knowledge
                            from .infrastructure import update_knowledge_for_ai
                            
                            console.print(f"\n[dim]📚 [#4682B4]Updating infrastructure knowledge...[/#4682B4][/dim]")
                            
                            result = update_knowledge_for_ai(gcp_config.get("project_id"))
                            
                            if result["success"]:
                                tool_result = result
                            else:
                                tool_result = {
                                    "success": False,
                                    "error": result.get("error", "Failed to update knowledge")
                                }

                        elif function_name == "ssh_execute_command":
                            # Execute SSH command
                            from .ssh import run_ssh_command
                            
                            host = function_args.get("host", "")
                            command = function_args.get("command", "")
                            
                            if not host or not command:
                                tool_result = {
                                    "success": False,
                                    "error": "Both 'host' and 'command' are required"
                                }
                            else:
                                console.print(f"\n[dim]🔐 [#4682B4]ssh {host}: {command}[/#4682B4][/dim]")
                                
                                result = run_ssh_command(
                                    host=host,
                                    command=command,
                                    timeout=60
                                )
                                
                                if result:
                                    # Truncate large outputs
                                    stdout = result["stdout"]
                                    stderr = result["stderr"]
                                    max_output_size = 10000  # 10KB limit for SSH
                                    
                                    if len(stdout) > max_output_size:
                                        stdout = stdout[:max_output_size] + "\n[Output truncated]"
                                    if len(stderr) > max_output_size:
                                        stderr = stderr[:max_output_size] + "\n[Output truncated]"
                                    
                                    tool_result = {
                                        "success": result["success"],
                                        "stdout": stdout,
                                        "stderr": stderr,
                                        "return_code": result["return_code"],
                                        "host": host,
                                        "command": command
                                    }
                                else:
                                    tool_result = {
                                        "success": False,
                                        "error": "Failed to execute SSH command",
                                        "host": host,
                                        "command": command
                                    }
                        
                        else:
                            # MCP tool execution
                            parts = function_name.split('_', 1)
                            if len(parts) == 2:
                                server_name, tool_name = parts
                                
                                console.print(f"\n[dim]🔧 Using MCP: {server_name}/{tool_name}[/dim]")
                                
                                conn = manager.get_connection(server_name)
                                if conn:
                                    tool_result = conn.call_tool(tool_name, function_args)
                                else:
                                    console.print(f"[yellow]Warning: MCP server '{server_name}' not connected[/yellow]")
                        
                        # Add assistant message with tool calls to history
                        chat_history.append({
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [{
                                "id": tool_call.id,
                                "type": "function",
                                "function": {
                                    "name": function_name,
                                    "arguments": tool_call.function.arguments or "{}"
                                }
                            }]
                        })
                        
                        # Add tool result to history (truncate if needed)
                        tool_result_str = json.dumps(tool_result) if tool_result else "{}"
                        max_tool_result_size = 30000  # 30KB limit
                        if len(tool_result_str) > max_tool_result_size:
                            # Try to truncate the output field if it exists
                            if tool_result and "output" in tool_result:
                                tool_result["output"] = tool_result["output"][:10000] + "\n[Truncated for context size]"
                                tool_result_str = json.dumps(tool_result)
                        
                        chat_history.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": tool_result_str
                        })
                        
                        # Get next response with error handling
                        try:
                            response = client.chat.completions.create(
                                model=model,
                                messages=chat_history,
                                tools=tools,
                                tool_choice="auto",
                                timeout=60.0
                            )
                            message = response.choices[0].message
                        except json.JSONDecodeError as e:
                            response_container["error"] = f"API response parsing error during tool execution: {str(e)}\n\nThe response was too large. Try asking for a summary or specific subset of data."
                            return
                        except Exception as e:
                            response_container["error"] = f"API error during tool execution: {str(e)}"
                            return
                    
                    # Final response
                    response_container["message"] = message.content.strip() if message.content else ""
                        
                except json.JSONDecodeError as e:
                    response_container["error"] = f"JSON parsing error: {str(e)}\n\nThis usually happens when:\n1. The API response is too large\n2. Network connection was interrupted\n3. The context is too long\n\nTry:\n- Asking a simpler question\n- Using /clear to reset conversation\n- Checking your internet connection"
                except Exception as e:
                    response_container["error"] = str(e)
                    import traceback
                    console.print(f"[red]Error in fetch_ai_response:[/red]")
                    traceback.print_exc()

            thread = Thread(target=fetch_ai_response, daemon=True)
            thread.start()

            with Live(spinner, refresh_per_second=12, transient=True):
                thread.join()

            if "error" in response_container:
                console.print(f"[red]API Error:[/red] {response_container['error']}")
                chat_history.pop()
                continue

            ai_message = response_container["message"]
            
            # Add final AI response to history
            if ai_message:
                if not (chat_history and 
                        chat_history[-1].get("role") == "assistant" and 
                        chat_history[-1].get("content") == ai_message):
                    chat_history.append({"role": "assistant", "content": ai_message})
            
            # Display AI response
            if ai_message:
                console.print(Panel(
                    ai_message, 
                    title="[bold #B8860B]Thoth[/bold #B8860B]",
                    border_style="#B8860B",
                    padding=(1, 2)
                ))

        except KeyboardInterrupt:
            console.print("\n[dim]Press Ctrl+C again or type /exit to quit[/dim]")
            continue
        except EOFError:
            console.print("\n[bold #B8860B]Until the stars speak again.[/bold #B8860B]")
            shutdown_mcp_servers()
            break
        except Exception as e:
            console.print(Panel(
                f"[red]Unexpected error:[/red]\n{str(e)}",
                border_style="red",
                padding=(1, 2)
            ))
            import traceback
            traceback.print_exc()
    
    # Ensure cleanup
    shutdown_mcp_servers()