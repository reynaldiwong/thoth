

from rich.align import Align
from rich.color import Color
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.style import Style
from rich.table import Table
from rich.text import Text
from typing import Optional
from .input import get_key

BANNER = """
████████╗ ██╗  ██╗  ▄▄■■■■■▄▄ ▀██████╗ ██╗  ██╗
╚══██╔══╝ ██║  ▌▄▄▄█▀  ▄▄▄  ▀█▄▄▄▐╔══╝ ██║  ██║
   ██║    █████▌════  █ ■ █  ════▐║    ███████║
   ██║    ██╔══▌▀▀▀█▄  ▀▀▀  ▄█▀▀▀▐║    ██╔══██║
   ██║    ██║  ██║  ▀▀■■■■■▀▀   ██║    ██║  ██║
   ╚═╝    ╚═╝  ╚═╝              ╚═╝    ╚═╝  ╚═╝
"""
TAGLINE = "𓅞  Desireth thou to know the deep, hidden secret? 𓅞"

console = Console()


def show_banner() -> None:
    
    banner_lines = BANNER.strip().split("\n")
    start_color = Color.parse("#332701").triplet
    end_color = Color.parse("#C2A14A").triplet
    max_width = max(len(line) for line in banner_lines)

    def color_for_position(col: int) -> str:
        ratio = col / (max_width - 1) if max_width > 1 else 0
        r = int(start_color[0] + (end_color[0] - start_color[0]) * ratio)
        g = int(start_color[1] + (end_color[1] - start_color[1]) * ratio)
        b = int(start_color[2] + (end_color[2] - start_color[2]) * ratio)
        return f"#{r:02x}{g:02x}{b:02x}"

    styled = Text()
    for line in banner_lines:
        for col, char in enumerate(line):
            styled.append(char, style=Style(color=color_for_position(col)))
        styled.append("\n")
    
    console.print(Align.center(styled))
    console.print(Align.center(Text(TAGLINE, style="italic #BDB76B")))
    console.print()


def select_with_arrows(
    options: dict,
    prompt_text: str = "Select an option",
    default_key: Optional[str] = None
) -> Optional[str]:
    
    option_keys = list(options.keys())
    if not option_keys:
        return None
    
    selected_index = (
        option_keys.index(default_key) if default_key in option_keys else 0
    )

    def create_panel() -> Panel:
        tbl = Table.grid(padding=(0, 2))
        tbl.add_column(style="cyan", width=3)
        tbl.add_column(style="white")
        
        for i, key in enumerate(option_keys):
            prefix = "▶" if i == selected_index else " "
            color = "[cyan]" if i == selected_index else "[white]"
            tbl.add_row(prefix, f"{color}{key}[/] [dim]({options[key]})[/dim]")
        
        tbl.add_row("", "")
        tbl.add_row("", "[dim]Use ↑/↓ to navigate, Enter to select, Esc to cancel[/dim]")
        return Panel(tbl, title=f"[bold]{prompt_text}[/bold]", border_style="#B8860B")

    with Live(create_panel(), console=console, transient=True, auto_refresh=False) as live:
        while True:
            try:
                key = get_key()
                
                if key == "up":
                    selected_index = (selected_index - 1) % len(option_keys)
                    live.update(create_panel(), refresh=True)
                elif key == "down":
                    selected_index = (selected_index + 1) % len(option_keys)
                    live.update(create_panel(), refresh=True)
                elif key == "enter":
                    return option_keys[selected_index]
                elif key == "escape":
                    return None
            except KeyboardInterrupt:
                return None


def select_model_interactive(
    model_list: list[str],
    per_page: int = 15  
) -> Optional[str]:
    """
    Interactive model selector with pagination and search.
    
    Controls:
    - UP/DOWN: Navigate within page
    - LEFT/RIGHT: Change page
    - Type: Filter models
    - BACKSPACE: Edit search query
    - ENTER: Select model
    - ESC: Cancel
    """
    if not model_list:
        return None

    search_query = ""
    filtered = model_list.copy()
    page = 0
    selected_index = 0

    def total_pages() -> int:
        return max(1, (len(filtered) + per_page - 1) // per_page)

    def get_page_items() -> list[str]:
        start = page * per_page
        return filtered[start:start + per_page]

    def create_panel() -> Panel:
        tbl = Table.grid(padding=(0, 1))
        tbl.add_column(width=3, style="cyan")
        tbl.add_column(style="white", ratio=1)
        
        for i, model_name in enumerate(get_page_items()):
            prefix = "▶" if i == selected_index else " "
            tbl.add_row(prefix, f"[cyan]{model_name}[/cyan]")
        
        info = (
            f"Page {page + 1}/{total_pages()} • "
            f"{len(filtered)} models • "
            f"Search: [bold]{search_query or '—'}[/bold]"
        )
        footer = (
            "[dim]↑/↓ select • ←/→ page • type to search • "
            "BACKSPACE to edit • Enter to choose • ctrl^C to cancel[/dim]"
        )
        return Panel(
            tbl,
            title="Choose Model",
            subtitle=f"{info}\n{footer}",
            border_style="#B8860B"
        )

    with Live(create_panel(), console=console, transient=True, auto_refresh=False) as live:
        while True:
            key = get_key()
            page_items = get_page_items()
            
            if key == "up":
                selected_index = (selected_index - 1) % min(per_page, len(page_items) or 1)
            elif key == "down":
                selected_index = (selected_index + 1) % min(per_page, len(page_items) or 1)
            elif key == "left" and page > 0:
                page -= 1
                selected_index = 0
            elif key == "right" and page < total_pages() - 1:
                page += 1
                selected_index = 0
            elif key == "backspace" and search_query:
                search_query = search_query[:-1]
                filtered = [m for m in model_list if search_query.lower() in m.lower()]
                page = 0
                selected_index = 0
            elif key == "enter":
                return page_items[selected_index] if page_items else None
            elif key == "escape":
                return None
            elif isinstance(key, str) and len(key) == 1 and key.isprintable():
                search_query += key
                filtered = [m for m in model_list if search_query.lower() in m.lower()]
                page = 0
                selected_index = 0
            
            
            if page >= total_pages():
                page = max(0, total_pages() - 1)
                selected_index = 0
            
            live.update(create_panel(), refresh=True)