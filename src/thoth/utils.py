

from pathlib import Path


def load_system_prompt_from_md(file_path: str = "./prompts/prompt.md") -> str:
    
    path = Path(file_path)
    
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Prompt file not found: {file_path}")
    
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        raise ValueError(f"Prompt file '{file_path}' is empty.")
    
    return content