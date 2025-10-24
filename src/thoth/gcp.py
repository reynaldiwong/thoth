import json
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, List
from rich.panel import Panel
from rich.table import Table
from prompt_toolkit import prompt
from prompt_toolkit.formatted_text import HTML
from .display import console, select_with_arrows
from .crypto import encrypt_value, decrypt_value

GCP_CONFIG_PATH = Path.home() / ".thoth_gcp_config.json"


GCP_REGIONS = {
    "us-central1 (Iowa)": "us-central1",
    "us-east1 (South Carolina)": "us-east1",
    "us-east4 (Northern Virginia)": "us-east4",
    "us-west1 (Oregon)": "us-west1",
    "us-west2 (Los Angeles)": "us-west2",
    "us-west3 (Salt Lake City)": "us-west3",
    "us-west4 (Las Vegas)": "us-west4",
    "europe-west1 (Belgium)": "europe-west1",
    "europe-west2 (London)": "europe-west2",
    "europe-west3 (Frankfurt)": "europe-west3",
    "europe-west4 (Netherlands)": "europe-west4",
    "europe-central2 (Warsaw)": "europe-central2",
    "asia-east1 (Taiwan)": "asia-east1",
    "asia-east2 (Hong Kong)": "asia-east2",
    "asia-northeast1 (Tokyo)": "asia-northeast1",
    "asia-northeast2 (Osaka)": "asia-northeast2",
    "asia-northeast3 (Seoul)": "asia-northeast3",
    "asia-south1 (Mumbai)": "asia-south1",
    "asia-southeast1 (Singapore)": "asia-southeast1",
    "asia-southeast2 (Jakarta)": "asia-southeast2",
    "australia-southeast1 (Sydney)": "australia-southeast1",
}


def get_zones_for_region(region: str) -> Dict[str, str]:
    
    
    zones = {}
    for suffix in ['a', 'b', 'c', 'd', 'e', 'f']:
        zone = f"{region}-{suffix}"
        zones[f"{zone}"] = zone
    return zones


def check_gcloud_auth() -> Optional[Dict[str, str]]:
    """
    Check if user is authenticated with gcloud and return account info.
    
    Returns:
        Dict with account info if authenticated, None otherwise
    """
    try:
        result = subprocess.run(
            ["gcloud", "auth", "list", "--format=json"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            return None
        
        accounts = json.loads(result.stdout)
        
        # Find active account
        active_account = None
        for account in accounts:
            if account.get("status") == "ACTIVE":
                active_account = {
                    "email": account.get("account"),
                    "status": account.get("status")
                }
                break
        
        return active_account
        
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return None
    except Exception as e:
        console.print(f"[yellow]Error checking gcloud auth: {e}[/yellow]")
        return None


def get_all_gcloud_accounts() -> List[Dict[str, str]]:
    """
    Get all gcloud accounts.
    
    Returns:
        List of account dicts with email and status
    """
    try:
        result = subprocess.run(
            ["gcloud", "auth", "list", "--format=json"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            return []
        
        accounts = json.loads(result.stdout)
        return accounts
        
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return []
    except Exception as e:
        console.print(f"[yellow]Error getting accounts: {e}[/yellow]")
        return []


def switch_gcloud_account(account_email: str) -> bool:
    """
    Switch to a different gcloud account.
    
    Args:
        account_email: Email of the account to switch to
    
    Returns:
        True if successful, False otherwise
    """
    try:
        result = subprocess.run(
            ["gcloud", "config", "set", "account", account_email],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            return True
        else:
            console.print(f"[red]Failed to switch account: {result.stderr}[/red]")
            return False
            
    except Exception as e:
        console.print(f"[red]Error switching account: {e}[/red]")
        return False


def prompt_gcloud_login() -> bool:
    """
    Prompt user to login with gcloud.
    
    Returns:
        True if login successful, False otherwise
    """
    console.print("\n[cyan]Opening browser for gcloud authentication...[/cyan]")
    console.print("[dim]This will open a browser window for authentication.[/dim]\n")
    
    try:
        result = subprocess.run(
            ["gcloud", "auth", "login"],
            timeout=300  # 5 minutes timeout
        )
        
        if result.returncode == 0:
            console.print("\n[green]✓ Authentication successful![/green]\n")
            return True
        else:
            console.print("\n[red]✗ Authentication failed[/red]\n")
            return False
            
    except subprocess.TimeoutExpired:
        console.print("\n[red]✗ Authentication timed out[/red]\n")
        return False
    except Exception as e:
        console.print(f"\n[red]✗ Authentication error: {e}[/red]\n")
        return False


def configure_gcloud_account_interactive() -> None:
    """
    Interactive menu to manage gcloud accounts.
    """
    console.print("\n[bold cyan]🔐 GCloud Account Management[/bold cyan]\n")
    
    # Get all accounts
    accounts = get_all_gcloud_accounts()
    
    if not accounts:
        console.print("[yellow]No gcloud accounts found.[/yellow]\n")
        from rich.prompt import Confirm
        if Confirm.ask("Would you like to login now?", default=True):
            if prompt_gcloud_login():
                # Refresh accounts list
                accounts = get_all_gcloud_accounts()
            else:
                return
        else:
            return
    
    # Build options dict
    options = {}
    current_account = None
    
    for account in accounts:
        email = account.get("account")
        status = account.get("status")
        is_active = status == "ACTIVE"
        
        if is_active:
            current_account = email
            options[f"{email} 🟢"] = email
        else:
            options[email] = email
    
    # Add login option
    options["Login with a new account"] = "login_new"
    options["Back"] = "back"
    
    # Show current account
    if current_account:
        console.print(f"[green]Current account:[/green] [bold]{current_account}[/bold]\n")
    
    # Select account
    choice = select_with_arrows(options, prompt_text="Select GCloud Account")
    
    if not choice or choice == "Back":
        return
    
    selected = options[choice]
    
    if selected == "login_new":
        # Login with new account
        if prompt_gcloud_login():
            # Get the newly logged in account
            auth_info = check_gcloud_auth()
            if auth_info:
                new_email = auth_info.get("email")
                console.print(f"[green]✓ Logged in as: {new_email}[/green]\n")
                
                # Update config
                config = load_gcp_config()
                config["authenticated_account"] = new_email
                save_gcp_config(config)
    elif selected == "back":
        return
    else:
        # Switch to selected account
        if selected != current_account:
            console.print(f"\n[dim]Switching to account: {selected}...[/dim]")
            
            if switch_gcloud_account(selected):
                console.print(f"[green]✓ Switched to account: {selected}[/green]\n")
                
                # Update config
                config = load_gcp_config()
                config["authenticated_account"] = selected
                save_gcp_config(config)
            else:
                console.print(f"[red]✗ Failed to switch account[/red]\n")
        else:
            console.print(f"[dim]Already using account: {selected}[/dim]\n")


def run_gcloud_command(args: List[str], project_id: Optional[str] = None) -> Optional[str]:
    """
    Run a gcloud command and return the output.
    
    Args:
        args: List of gcloud command arguments (e.g., ['compute', 'instances', 'list'])
        project_id: Optional project ID to use
    
    Returns:
        Command output as string, or None if failed
    """
    try:
        cmd = ['gcloud'] + args
        
        
        if project_id and '--project' not in args:
            cmd.extend(['--project', project_id])
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            return result.stdout
        else:
            console.print(f"[red]gcloud error:[/red] {result.stderr}")
            return None
    except subprocess.TimeoutExpired:
        console.print("[red]gcloud command timed out[/red]")
        return None
    except FileNotFoundError:
        console.print("[red]gcloud CLI not found. Please install Google Cloud SDK.[/red]")
        return None
    except Exception as e:
        console.print(f"[red]Error running gcloud: {e}[/red]")
        return None


def load_gcp_config() -> Dict[str, Any]:
    
    if not GCP_CONFIG_PATH.exists():
        return {}
    
    try:
        data = json.loads(GCP_CONFIG_PATH.read_text(encoding="utf-8"))
        
        if data.get("service_account_key"):
            data["service_account_key"] = decrypt_value(data["service_account_key"])
        return data
    except Exception as e:
        console.print(f"[red]Error loading GCP config: {e}[/red]")
        return {}


def save_gcp_config(config: Dict[str, Any]) -> None:
    
    config_copy = config.copy()
    
    
    if config_copy.get("service_account_key"):
        config_copy["service_account_key"] = f"encrypted:{encrypt_value(config_copy['service_account_key'])}"
    
    GCP_CONFIG_PATH.write_text(json.dumps(config_copy, indent=2), encoding="utf-8")
    GCP_CONFIG_PATH.chmod(0o600)


def configure_gcp_interactive() -> None:
    
    config = load_gcp_config()
    
    while True:
        console.print("\n[bold cyan]☁️  GCP Configuration[/bold cyan]\n")
        
        options = {
            "Set Project ID": "project",
            "Set Default Region": "region",
            "Set Default Zone": "zone",
            "Set GCloud Account": "account",
            "Set Service Account Key": "service_account",
            "View Current Config": "view",
            "Test gcloud Connection": "test",
            "Clear Config": "clear",
            "Back": "back"
        }
        
        choice = select_with_arrows(options, prompt_text="GCP Configuration Menu")
        
        if not choice or choice == "Back":
            break
        
        action = options[choice]
        
        if action == "project":
            current = config.get("project_id", "")
            console.print(f"\n[dim]Current: {current or 'Not set'}[/dim]\n")
            
            project_id = prompt(HTML("<b>GCP Project ID</b>: ")).strip()
            if project_id:
                config["project_id"] = project_id
                save_gcp_config(config)
                console.print(f"[green]✓ Project ID set to: {project_id}[/green]\n")
        
        elif action == "region":
            current = config.get("region", "")
            console.print(f"\n[dim]Current: {current or 'Not set'}[/dim]\n")
            
            selected_region = select_with_arrows(
                GCP_REGIONS,
                prompt_text="Select Default Region"
            )
            
            if selected_region:
                region = GCP_REGIONS[selected_region]
                config["region"] = region
                save_gcp_config(config)
                console.print(f"[green]✓ Region set to: {region}[/green]\n")
        
        elif action == "zone":
            current_region = config.get("region", "")
            current_zone = config.get("zone", "")
            
            if not current_region:
                console.print("[yellow]Please set a region first[/yellow]\n")
                continue
            
            console.print(f"\n[dim]Current: {current_zone or 'Not set'}[/dim]")
            console.print(f"[dim]Region: {current_region}[/dim]\n")
            
            zones = get_zones_for_region(current_region)
            selected_zone = select_with_arrows(
                zones,
                prompt_text=f"Select Zone in {current_region}"
            )
            
            if selected_zone:
                zone = zones[selected_zone]
                config["zone"] = zone
                save_gcp_config(config)
                console.print(f"[green]✓ Zone set to: {zone}[/green]\n")
        
        elif action == "account":
            configure_gcloud_account_interactive()
        
        elif action == "service_account":
            console.print("\n[dim]Enter the path to your service account JSON key file[/dim]\n")
            
            key_path = prompt(HTML("<b>Service Account Key Path</b>: ")).strip()
            if key_path:
                try:
                    key_file = Path(key_path).expanduser()
                    if key_file.exists():
                        key_content = key_file.read_text()
                        
                        json.loads(key_content)
                        config["service_account_key"] = key_content
                        save_gcp_config(config)
                        console.print(f"[green]✓ Service account key saved[/green]\n")
                    else:
                        console.print(f"[red]File not found: {key_path}[/red]\n")
                except json.JSONDecodeError:
                    console.print(f"[red]Invalid JSON file[/red]\n")
                except Exception as e:
                    console.print(f"[red]Error: {e}[/red]\n")
        
        elif action == "view":
            show_gcp_config(config)
        
        elif action == "test":
            test_gcloud_connection(config)
        
        elif action == "clear":
            from rich.prompt import Confirm
            if Confirm.ask("[yellow]Clear all GCP configuration?[/yellow]"):
                GCP_CONFIG_PATH.unlink(missing_ok=True)
                config = {}
                console.print("[green]✓ GCP configuration cleared[/green]\n")


def test_gcloud_connection(config: Dict[str, Any]) -> None:
    
    console.print("\n[dim]Testing gcloud connection...[/dim]\n")
    
    
    try:
        result = subprocess.run(
            ['gcloud', 'version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode != 0:
            console.print("[red]✗ gcloud CLI not found[/red]")
            console.print("[dim]Install: https://cloud.google.com/sdk/docs/install[/dim]\n")
            return
        
        console.print("[green]✓ gcloud CLI installed[/green]")
    except Exception:
        console.print("[red]✗ gcloud CLI not found[/red]")
        console.print("[dim]Install: https://cloud.google.com/sdk/docs/install[/dim]\n")
        return
    
    
    result = subprocess.run(
        ['gcloud', 'auth', 'list', '--format=json'],
        capture_output=True,
        text=True,
        timeout=5
    )
    
    if result.returncode == 0:
        try:
            accounts = json.loads(result.stdout)
            if accounts:
                active_account = None
                for account in accounts:
                    if account.get("status") == "ACTIVE":
                        active_account = account.get("account")
                        break
                
                if active_account:
                    console.print(f"[green]✓ Authenticated as: {active_account}[/green]")
                else:
                    console.print(f"[green]✓ Authenticated ({len(accounts)} account(s))[/green]")
            else:
                console.print("[yellow]⚠ Not authenticated[/yellow]")
                console.print("[dim]Run: gcloud auth login[/dim]")
        except:
            console.print("[yellow]⚠ Could not verify authentication[/yellow]")
    
    
    project_id = config.get("project_id")
    if project_id:
        result = subprocess.run(
            ['gcloud', 'projects', 'describe', project_id, '--format=json'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            console.print(f"[green]✓ Project '{project_id}' accessible[/green]")
        else:
            console.print(f"[yellow]⚠ Cannot access project '{project_id}'[/yellow]")
    else:
        console.print("[dim]○ No project configured[/dim]")
    
    console.print()


def show_gcp_config(config: Dict[str, Any]) -> None:
    
    if not config:
        console.print("[yellow]No GCP configuration set[/yellow]\n")
        return
    
    table = Table(title="Current GCP Configuration", border_style="cyan")
    table.add_column("Setting", style="cyan", no_wrap=True)
    table.add_column("Value", style="white")
    
    table.add_row("Project ID", config.get("project_id", "[dim]Not set[/dim]"))
    table.add_row("Region", config.get("region", "[dim]Not set[/dim]"))
    table.add_row("Zone", config.get("zone", "[dim]Not set[/dim]"))
    
    # Show authenticated account
    auth_account = config.get("authenticated_account")
    if auth_account:
        table.add_row("GCloud Account", f"[green]{auth_account}[/green]")
    else:
        table.add_row("GCloud Account", "[dim]Not set[/dim]")
    
    table.add_row(
        "Service Account", 
        "[green]✓ Configured[/green]" if config.get("service_account_key") else "[dim]Not set[/dim]"
    )
    
    console.print(table)
    console.print()


def get_gcp_context_for_ai() -> str:
    
    from .utils import load_system_prompt_from_md
    
    config = load_gcp_config()
    
    if not config:
        return ""
    
    
    try:
        gcp_context_template = load_system_prompt_from_md("./prompts/gcp_context.md")
    except (FileNotFoundError, ValueError):
        
        gcp_context_template = "[GCP Configuration Available]\n"
    
    
    context = "\n\n[Current GCP Configuration]:\n"
    
    if config.get("project_id"):
        context += f"  • Project ID: {config['project_id']}\n"
    
    if config.get("region"):
        context += f"  • Default Region: {config['region']}\n"
    
    if config.get("zone"):
        context += f"  • Default Zone: {config['zone']}\n"
    
    # Show authenticated account
    auth_account = config.get("authenticated_account")
    if auth_account:
        context += f"  • GCloud Account: {auth_account}\n"
    
    if config.get("service_account_key"):
        context += "  • Service Account: Configured\n"
    
    
    context += "\n" + gcp_context_template
    
    return context


def reset_gcp_config() -> None:
    
    GCP_CONFIG_PATH.unlink(missing_ok=True)
    console.print("[green]✓ GCP configuration reset[/green]\n")



def list_gcp_instances(project_id: str) -> Optional[str]:
    
    return run_gcloud_command(
        ['compute', 'instances', 'list', '--format=table(name,zone,machineType,status,networkInterfaces[0].accessConfigs[0].natIP:label=EXTERNAL_IP)'],
        project_id=project_id
    )


def describe_gcp_instance(instance_name: str, zone: str, project_id: str) -> Optional[str]:
    
    return run_gcloud_command(
        ['compute', 'instances', 'describe', instance_name, '--zone', zone],
        project_id=project_id
    )


def list_gcp_buckets(project_id: str) -> Optional[str]:
    
    return run_gcloud_command(
        ['storage', 'buckets', 'list'],
        project_id=project_id
    )


def list_gcp_services(project_id: str) -> Optional[str]:
    
    return run_gcloud_command(
        ['services', 'list', '--enabled'],
        project_id=project_id
    )