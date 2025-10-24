import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Confirm
from .display import console, select_with_arrows
from .gcp import load_gcp_config, run_gcloud_command


def get_knowledge_file_path(project_id: str) -> Path:
    
    knowledge_dir = Path.home() / ".thoth_knowledge"
    knowledge_dir.mkdir(exist_ok=True)
    return knowledge_dir / f"{project_id}_infrastructure.json"


def has_stored_knowledge(project_id: str) -> bool:
    
    knowledge_file = get_knowledge_file_path(project_id)
    return knowledge_file.exists()


def analyze_infrastructure(project_id: str, silent: bool = False) -> Optional[Dict[str, Any]]:
    """
    Analyze GCP infrastructure and store knowledge.
    
    Args:
        project_id: GCP project ID
        silent: If True, don't print progress messages
    
    Returns:
        Dict with infrastructure knowledge or None if failed
    """
    if not silent:
        console.print(f"\n[cyan]🔍 Analyzing infrastructure for project: {project_id}[/cyan]\n")
    
    knowledge = {
        "project_id": project_id,
        "timestamp": datetime.now().isoformat(),
        "compute_instances": [],
        "networks": [],
        "firewall_rules": [],
        "load_balancers": []
    }
    
    
    if not silent:
        console.print("[dim]Fetching compute instances...[/dim]")
    
    output = run_gcloud_command(
        ["compute", "instances", "list", "--format=json"],
        project_id=project_id
    )
    
    if output:
        try:
            instances = json.loads(output)
            for instance in instances:
                vm_info = {
                    "name": instance.get("name"),
                    "zone": instance.get("zone", "").split("/")[-1],
                    "machine_type": instance.get("machineType", "").split("/")[-1],
                    "status": instance.get("status"),
                    "internal_ip": None,
                    "external_ip": None,
                    "tags": instance.get("tags", {}).get("items", [])
                }
                
                
                for interface in instance.get("networkInterfaces", []):
                    if interface.get("networkIP"):
                        vm_info["internal_ip"] = interface["networkIP"]
                    
                    for config in interface.get("accessConfigs", []):
                        if config.get("natIP"):
                            vm_info["external_ip"] = config["natIP"]
                
                knowledge["compute_instances"].append(vm_info)
            
            if not silent:
                console.print(f"[green]✓ Found {len(instances)} compute instances[/green]")
        except json.JSONDecodeError:
            if not silent:
                console.print("[yellow]⚠ Could not parse compute instances[/yellow]")
    
    
    if not silent:
        console.print("[dim]Fetching networks...[/dim]")
    
    output = run_gcloud_command(
        ["compute", "networks", "list", "--format=json"],
        project_id=project_id
    )
    
    if output:
        try:
            networks = json.loads(output)
            for network in networks:
                net_info = {
                    "name": network.get("name"),
                    "auto_create_subnetworks": network.get("autoCreateSubnetworks"),
                    "subnets": []
                }
                
                
                subnet_output = run_gcloud_command(
                    ["compute", "networks", "subnets", "list", 
                     f"--network={network.get('name')}", "--format=json"],
                    project_id=project_id
                )
                
                if subnet_output:
                    try:
                        subnets = json.loads(subnet_output)
                        for subnet in subnets:
                            net_info["subnets"].append({
                                "name": subnet.get("name"),
                                "region": subnet.get("region", "").split("/")[-1],
                                "ip_range": subnet.get("ipCidrRange")
                            })
                    except json.JSONDecodeError:
                        pass
                
                knowledge["networks"].append(net_info)
            
            if not silent:
                console.print(f"[green]✓ Found {len(networks)} networks[/green]")
        except json.JSONDecodeError:
            if not silent:
                console.print("[yellow]⚠ Could not parse networks[/yellow]")
    
    
    if not silent:
        console.print("[dim]Fetching firewall rules...[/dim]")
    
    output = run_gcloud_command(
        ["compute", "firewall-rules", "list", "--format=json"],
        project_id=project_id
    )
    
    if output:
        try:
            rules = json.loads(output)
            for rule in rules:
                rule_info = {
                    "name": rule.get("name"),
                    "network": rule.get("network", "").split("/")[-1],
                    "direction": rule.get("direction"),
                    "priority": rule.get("priority"),
                    "action": "ALLOW" if rule.get("allowed") else "DENY",
                    "source_ranges": rule.get("sourceRanges", []),
                    "target_tags": rule.get("targetTags", []),
                    "allowed": rule.get("allowed", []),
                    "denied": rule.get("denied", [])
                }
                
                knowledge["firewall_rules"].append(rule_info)
            
            if not silent:
                console.print(f"[green]✓ Found {len(rules)} firewall rules[/green]")
        except json.JSONDecodeError:
            if not silent:
                console.print("[yellow]⚠ Could not parse firewall rules[/yellow]")
    
    
    if not silent:
        console.print("[dim]Fetching load balancers...[/dim]")
    
    output = run_gcloud_command(
        ["compute", "forwarding-rules", "list", "--format=json"],
        project_id=project_id
    )
    
    if output:
        try:
            lbs = json.loads(output)
            for lb in lbs:
                lb_info = {
                    "name": lb.get("name"),
                    "type": lb.get("loadBalancingScheme"),
                    "ip_address": lb.get("IPAddress"),
                    "region": lb.get("region", "").split("/")[-1] if lb.get("region") else "global",
                    "target": lb.get("target", "").split("/")[-1]
                }
                
                knowledge["load_balancers"].append(lb_info)
            
            if not silent:
                console.print(f"[green]✓ Found {len(lbs)} load balancers[/green]")
        except json.JSONDecodeError:
            if not silent:
                console.print("[yellow]⚠ Could not parse load balancers[/yellow]")
    
    
    knowledge_file = get_knowledge_file_path(project_id)
    knowledge_file.write_text(json.dumps(knowledge, indent=2), encoding="utf-8")
    
    if not silent:
        console.print(f"\n[green]✓ Infrastructure knowledge saved to {knowledge_file}[/green]\n")
    
    return knowledge


def analyze_infrastructure_interactive() -> None:
    
    gcp_config = load_gcp_config()
    
    if not gcp_config.get("project_id"):
        console.print("[yellow]No GCP project configured. Please configure GCP first.[/yellow]\n")
        return
    
    project_id = gcp_config["project_id"]
    
    
    if has_stored_knowledge(project_id):
        console.print(f"[yellow]Knowledge already exists for project: {project_id}[/yellow]")
        if not Confirm.ask("Re-analyze and update knowledge?"):
            return
    
    analyze_infrastructure(project_id, silent=False)


def view_stored_knowledge_interactive() -> None:
    
    gcp_config = load_gcp_config()
    
    if not gcp_config.get("project_id"):
        console.print("[yellow]No GCP project configured. Please configure GCP first.[/yellow]\n")
        return
    
    project_id = gcp_config["project_id"]
    knowledge_file = get_knowledge_file_path(project_id)
    
    if not knowledge_file.exists():
        console.print(f"[yellow]No knowledge found for project: {project_id}[/yellow]")
        console.print("[dim]Use /analyze to analyze infrastructure[/dim]\n")
        return
    
    try:
        knowledge = json.loads(knowledge_file.read_text(encoding="utf-8"))
        
        
        console.print(Panel(
            f"[bold]Project:[/bold] {knowledge.get('project_id')}\n"
            f"[bold]Last Updated:[/bold] {knowledge.get('timestamp')}\n\n"
            f"[cyan]Resources:[/cyan]\n"
            f"  • Compute Instances: {len(knowledge.get('compute_instances', []))}\n"
            f"  • Networks: {len(knowledge.get('networks', []))}\n"
            f"  • Firewall Rules: {len(knowledge.get('firewall_rules', []))}\n"
            f"  • Load Balancers: {len(knowledge.get('load_balancers', []))}",
            title="📚 Infrastructure Knowledge",
            border_style="cyan"
        ))
        
        
        menu_options = {
            "View Compute Instances": "vms",
            "View Networks": "networks",
            "View Firewall Rules": "firewall",
            "View Load Balancers": "lbs",
            "Refresh Knowledge": "refresh",
            "Back": "back"
        }
        
        choice = select_with_arrows(menu_options, prompt_text="Select option")
        
        if not choice or choice == "Back":
            return
        
        action = menu_options[choice]
        
        if action == "vms":
            table = Table(title="Compute Instances", border_style="cyan")
            table.add_column("Name", style="cyan")
            table.add_column("Zone", style="white")
            table.add_column("Type", style="white")
            table.add_column("Status", style="green")
            table.add_column("Internal IP", style="white")
            table.add_column("External IP", style="white")
            
            for vm in knowledge.get("compute_instances", []):
                table.add_row(
                    vm.get("name", ""),
                    vm.get("zone", ""),
                    vm.get("machine_type", ""),
                    vm.get("status", ""),
                    vm.get("internal_ip", "-"),
                    vm.get("external_ip", "-")
                )
            
            console.print(table)
            console.print()
        
        elif action == "networks":
            for net in knowledge.get("networks", []):
                table = Table(title=f"Network: {net.get('name')}", border_style="cyan")
                table.add_column("Subnet", style="cyan")
                table.add_column("Region", style="white")
                table.add_column("IP Range", style="white")
                
                for subnet in net.get("subnets", []):
                    table.add_row(
                        subnet.get("name", ""),
                        subnet.get("region", ""),
                        subnet.get("ip_range", "")
                    )
                
                console.print(table)
                console.print()
        
        elif action == "firewall":
            table = Table(title="Firewall Rules", border_style="cyan")
            table.add_column("Name", style="cyan")
            table.add_column("Network", style="white")
            table.add_column("Direction", style="white")
            table.add_column("Action", style="green")
            table.add_column("Priority", style="white")
            
            for rule in knowledge.get("firewall_rules", []):
                table.add_row(
                    rule.get("name", ""),
                    rule.get("network", ""),
                    rule.get("direction", ""),
                    rule.get("action", ""),
                    str(rule.get("priority", ""))
                )
            
            console.print(table)
            console.print()
        
        elif action == "lbs":
            table = Table(title="Load Balancers", border_style="cyan")
            table.add_column("Name", style="cyan")
            table.add_column("Type", style="white")
            table.add_column("IP Address", style="white")
            table.add_column("Region", style="white")
            
            for lb in knowledge.get("load_balancers", []):
                table.add_row(
                    lb.get("name", ""),
                    lb.get("type", ""),
                    lb.get("ip_address", ""),
                    lb.get("region", "")
                )
            
            console.print(table)
            console.print()
        
        elif action == "refresh":
            analyze_infrastructure(project_id, silent=False)
    
    except Exception as e:
        console.print(f"[red]Error loading knowledge: {e}[/red]\n")


def get_infrastructure_context_for_ai(project_id: str) -> str:
    
    knowledge_file = get_knowledge_file_path(project_id)
    
    if not knowledge_file.exists():
        return ""
    
    try:
        knowledge = json.loads(knowledge_file.read_text(encoding="utf-8"))
        
        context = "\n\n" + "="*80 + "\n"
        context += "INFRASTRUCTURE KNOWLEDGE BASE\n"
        context += "="*80 + "\n\n"
        
        context += f"Project: {project_id}\n"
        context += f"Last Updated: {knowledge.get('timestamp', 'Unknown')}\n\n"
        
        
        resource_counts = []
        
        if knowledge.get("compute_instances"):
            count = len(knowledge["compute_instances"])
            resource_counts.append(f"{count} VMs")
        
        if knowledge.get("networks"):
            count = len(knowledge["networks"])
            resource_counts.append(f"{count} Networks")
        
        if knowledge.get("firewall_rules"):
            count = len(knowledge["firewall_rules"])
            resource_counts.append(f"{count} Firewall Rules")
        
        if knowledge.get("load_balancers"):
            count = len(knowledge["load_balancers"])
            resource_counts.append(f"{count} Load Balancers")
        
        if resource_counts:
            context += f"Resources: {', '.join(resource_counts)}\n\n"
        
        
        if knowledge.get("compute_instances"):
            context += "COMPUTE INSTANCES:\n"
            for vm in knowledge["compute_instances"]:
                context += f"  • {vm.get('name')} ({vm.get('zone')})\n"
                context += f"    Status: {vm.get('status')}\n"
                context += f"    Machine Type: {vm.get('machine_type')}\n"
                if vm.get('internal_ip'):
                    context += f"    Internal IP: {vm.get('internal_ip')}\n"
                if vm.get('external_ip'):
                    context += f"    External IP: {vm.get('external_ip')}\n"
                if vm.get('tags'):
                    context += f"    Tags: {', '.join(vm.get('tags', []))}\n"
                context += "\n"
        
        if knowledge.get("networks"):
            context += "NETWORKS:\n"
            for net in knowledge["networks"]:
                context += f"  • {net.get('name')}\n"
                if net.get('subnets'):
                    context += f"    Subnets: {len(net.get('subnets', []))}\n"
                context += "\n"
        
        if knowledge.get("firewall_rules"):
            context += "FIREWALL RULES:\n"
            for rule in knowledge["firewall_rules"]:
                context += f"  • {rule.get('name')}\n"
                context += f"    Direction: {rule.get('direction')}\n"
                context += f"    Action: {rule.get('action')}\n"
                if rule.get('source_ranges'):
                    context += f"    Sources: {', '.join(rule.get('source_ranges', []))}\n"
                if rule.get('allowed'):
                    protocols = [f"{a.get('protocol', 'all')}" for a in rule.get('allowed', [])]
                    context += f"    Allowed: {', '.join(protocols)}\n"
                context += "\n"
        
        if knowledge.get("load_balancers"):
            context += "LOAD BALANCERS:\n"
            for lb in knowledge["load_balancers"]:
                context += f"  • {lb.get('name')}\n"
                context += f"    Type: {lb.get('type')}\n"
                if lb.get('ip_address'):
                    context += f"    IP: {lb.get('ip_address')}\n"
                context += "\n"
        
        context += "="*80 + "\n"
        
        return context
        
    except Exception as e:
        console.print(f"[yellow]Error loading infrastructure knowledge: {e}[/yellow]")
        return ""


def auto_refresh_knowledge(project_id: str) -> None:
    """
    Automatically refresh infrastructure knowledge after changes.
    This is called after infrastructure modifications.
    """
    console.print("\n[dim]📚 Updating infrastructure knowledge...[/dim]")
    analyze_infrastructure(project_id, silent=True)
    console.print("[dim]✓ Knowledge updated[/dim]\n")


def update_knowledge_for_ai(project_id: str) -> Dict[str, Any]:
    """
    Update infrastructure knowledge and return summary for AI.
    This is called when AI needs to refresh the knowledge base.
    
    Returns:
        Dict with success status and summary
    """
    console.print("\n[dim]📚 Updating infrastructure knowledge...[/dim]")
    
    knowledge = analyze_infrastructure(project_id, silent=True)
    
    if knowledge:
        console.print("[dim]✓ Knowledge updated[/dim]\n")
        
        # Return summary for AI
        return {
            "success": True,
            "project_id": project_id,
            "timestamp": knowledge.get("timestamp"),
            "summary": {
                "compute_instances": len(knowledge.get("compute_instances", [])),
                "networks": len(knowledge.get("networks", [])),
                "firewall_rules": len(knowledge.get("firewall_rules", [])),
                "load_balancers": len(knowledge.get("load_balancers", []))
            },
            "message": f"Infrastructure knowledge updated successfully. Found {len(knowledge.get('compute_instances', []))} VMs, {len(knowledge.get('networks', []))} networks, {len(knowledge.get('firewall_rules', []))} firewall rules, and {len(knowledge.get('load_balancers', []))} load balancers."
        }
    else:
        console.print("[yellow]⚠ Failed to update knowledge[/yellow]\n")
        return {
            "success": False,
            "error": "Failed to analyze infrastructure"
        }