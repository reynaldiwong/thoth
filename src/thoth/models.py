from typing import Tuple, List
import getpass
from openai import OpenAI
from .config import load_config, save_config
from .display import console, select_with_arrows, select_model_interactive


PROVIDERS = {
    "OpenAI": "api.openai.com",
    "OpenRouter": "openrouter.ai"
}


def fetch_openai_models(api_key: str) -> List[str]:
    """Fetch available models from OpenAI."""
    try:
        client = OpenAI(api_key=api_key)
        models = client.models.list()
        
        chat_models = [
            model.id for model in models.data 
            if any(prefix in model.id for prefix in ["gpt-4", "gpt-3.5"])
        ]
        return sorted(chat_models, reverse=True)
    except Exception as e:
        error_msg = str(e).lower()
        if "authentication" in error_msg or "api key" in error_msg or "401" in error_msg:
            raise ValueError("Invalid API key. Please check your OpenAI API key.")
        elif "rate limit" in error_msg or "429" in error_msg:
            raise ValueError("Rate limit exceeded. Please try again later.")
        elif "network" in error_msg or "connection" in error_msg:
            raise ValueError("Network error. Please check your internet connection.")
        else:
            raise ValueError(f"Error fetching OpenAI models: {e}")


def fetch_openrouter_models(api_key: str) -> List[str]:
    """Fetch available models from OpenRouter."""
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
        
        # Check for authentication errors
        if response.status_code == 401:
            raise ValueError("Invalid API key. Please check your OpenRouter API key.")
        elif response.status_code == 429:
            raise ValueError("Rate limit exceeded. Please try again later.")
        elif response.status_code >= 500:
            raise ValueError("OpenRouter server error. Please try again later.")
        
        response.raise_for_status()
        
        models_data = response.json()
        
        model_ids = [model["id"] for model in models_data.get("data", [])]
        
        if not model_ids:
            raise ValueError("No models available from OpenRouter.")
        
        # Sort models by priority
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
    
    except requests.exceptions.Timeout:
        raise ValueError("Request timeout. Please check your internet connection.")
    except requests.exceptions.ConnectionError:
        raise ValueError("Connection error. Please check your internet connection.")
    except ValueError:
        # Re-raise our custom ValueError messages
        raise
    except Exception as e:
        raise ValueError(f"Error fetching OpenRouter models: {e}")


def choose_provider_and_model(reset: bool = False) -> Tuple[OpenAI, str, str]:
    """
    Choose AI provider and model, either from saved config or interactively.
    
    Returns:
        Tuple of (OpenAI client, provider name, model name)
    """
    config = {} if reset else load_config()
    
    # Choose provider
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
    
    # Get API key
    if config.get("api_key") and not reset:
        api_key = config["api_key"]
    else:
        console.print(f"\n[bold]Enter your {provider} API key:[/bold]")
        console.print("[dim](Your input will be hidden)[/dim]")
        api_key = getpass.getpass("API Key: ").strip()
        
        if not api_key:
            console.print("[red]No API key provided. Exiting.[/red]")
            raise SystemExit(1)
    
    # Choose model
    if config.get("model") and not reset:
        model = config["model"]
    else:
        # Fetch models dynamically with validation
        console.print(f"[dim]Validating API key and fetching models from {provider}...[/dim]")
        
        try:
            if provider == "OpenAI":
                model_list = fetch_openai_models(api_key)
            else:  # OpenRouter
                model_list = fetch_openrouter_models(api_key)
            
            console.print(f"[green]✓ API key validated successfully[/green]")
            console.print(f"[green]✓ Found {len(model_list)} models[/green]\n")
        
        except ValueError as e:
            console.print(f"[red]✗ API key validation failed[/red]")
            console.print(f"[red]{str(e)}[/red]\n")
            raise SystemExit(1)
        except Exception as e:
            console.print(f"[red]✗ Unexpected error during validation[/red]")
            console.print(f"[red]{str(e)}[/red]\n")
            raise SystemExit(1)
        
        model = select_model_interactive(model_list)
        if not model:
            console.print("[red]No model selected. Exiting.[/red]")
            raise SystemExit(1)
    
    # Create client
    if provider == "OpenAI":
        client = OpenAI(api_key=api_key)
    else:  # OpenRouter
        client = OpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1"
        )
    
    # Save configuration
    if not config or reset:
        save_config(provider, api_key, model)
        console.print(f"[green]Configuration saved for {provider} - {model}[/green]\n")
    
    return client, provider, model