

import sys
import typer
from dotenv import load_dotenv
from .display import show_banner, console
from .models import choose_provider_and_model
from .repl import run_repl

load_dotenv()

app = typer.Typer(add_completion=False, invoke_without_command=True)


@app.callback()
def main(
    ctx: typer.Context,
    reset: bool = typer.Option(
        False,
        "--reset",
        help="Reset saved provider, model and secret key"
    )
) -> None:
    """
    Thoth CLI - Interactive AI Shell
    
    A beautiful terminal interface for chatting with AI models.
    Supports OpenAI and OpenRouter providers with encrypted credential storage.
    """
    if ctx.invoked_subcommand is None and "--help" not in sys.argv:
        show_banner()
        try:
            client, provider, model = choose_provider_and_model(reset=reset)
            run_repl(client, provider, model)
        except (typer.Exit, KeyboardInterrupt):
            console.print("\n[#B8860B]Until the stars speak again.[/#B8860B]")
        finally:
            raise typer.Exit()