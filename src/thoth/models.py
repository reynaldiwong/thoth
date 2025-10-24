

from typing import Tuple, List
from openai import OpenAI
from .config import load_config, save_config
from .display import console, select_with_arrows, select_model_interactive


PROVIDERS = {
    "OpenAI": "api.openai.com",
    "OpenRouter": "openrouter.ai"
}


def fetch_openai_models(api_key: str) -> List[str]:
    
    try:
        client = OpenAI(api_key=api_key)
        models = client.models.list()
        
        chat_models = [
            model.id for model in models.data 
            if any(prefix in model.id for prefix in ["gpt-4", "gpt-3.5"])
        ]
        return sorted(chat_models, reverse=True)
    except Exception as e:
        console.print(f"[red]Error fetching OpenAI models: {e}[/red]")
        raise SystemExit(1)


def fetch_openrouter_models(api_key: str) -> List[str]:
    
    try:
        import requests
        
        response = requests.get(
            "https://openrouter.ai/api/v1/models",
            headers={
                "Authorization": f"Bearer {api_key}",
                "HTTP-Referer": "https://github.com/yourusername/thoth",
                "X-Title": "Thoth CLI"
            },
            timeout=10
        )
        response.raise_for_status()
        
        models_data = response.json()
        
        model_ids = [model["id"] for model in models_data.get("data", [])]
        
        
        priority_prefixes = [
            "anthropic/claude-3.5",
            "anthropic/claude-3",
            "openai/gpt-4",
            "google/gemini",
            "meta-llama/llama-3",
            "mistralai/",
            "deepseek/",
        ]
        
        def sort_key(model_id: str) -> tuple:
            for i, prefix in enumerate(priority_prefixes):
                if model_id.startswith(prefix):
                    return (i, model_id)
            return (len(priority_prefixes), model_id)
        
        return sorted(model_ids, key=sort_key)
    
    except Exception as e:
        console.print(f"[red]Error fetching OpenRouter models: {e}[/red]")
        raise SystemExit(1)


def choose_provider_and_model(reset: bool = False) -> Tuple[OpenAI, str, str]:
    """
    Choose AI provider and model, either from saved config or interactively.
    
    Returns:
        Tuple of (OpenAI client, provider name, model name)
    """
    config = {} if reset else load_config()
    
    
    if config.get("provider") and not reset:
        provider = config["provider"]
    else:
        provider = select_with_arrows(
            PROVIDERS,
            prompt_text="Select AI Provider"
        )
        if not provider:
            console.print("[red]No provider selected. Exiting.[/red]")
            raise SystemExit(1)
    
    
    if config.get("api_key") and not reset:
        api_key = config["api_key"]
    else:
        from rich.prompt import Prompt
        api_key = Prompt.ask(
            f"[bold]Enter your {provider} API key[/bold]",
            password=True
        ).strip()
        if not api_key:
            console.print("[red]No API key provided. Exiting.[/red]")
            raise SystemExit(1)
    
    
    if config.get("model") and not reset:
        model = config["model"]
    else:
        
        console.print(f"[dim]Fetching available models from {provider}...[/dim]")
        
        if provider == "OpenAI":
            model_list = fetch_openai_models(api_key)
        else:  
            model_list = fetch_openrouter_models(api_key)
        
        if not model_list:
            console.print(f"[red]No models available from {provider}. Exiting.[/red]")
            raise SystemExit(1)
        
        console.print(f"[green]✓ Found {len(model_list)} models[/green]\n")
        
        model = select_model_interactive(model_list)
        if not model:
            console.print("[red]No model selected. Exiting.[/red]")
            raise SystemExit(1)
    
    
    if provider == "OpenAI":
        client = OpenAI(api_key=api_key)
    else:  
        client = OpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1"
        )
    
    
    if not config or reset:
        save_config(provider, api_key, model)
        console.print(f"[green]Configuration saved for {provider} - {model}[/green]\n")
    
    return client, provider, model