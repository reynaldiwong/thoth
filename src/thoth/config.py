

import json
from pathlib import Path
from .crypto import encrypt_value, decrypt_value, SECRET_PATH

CONFIG_PATH = Path.home() / ".thoth_config.json"


def load_config() -> dict:
    
    if not CONFIG_PATH.exists():
        return {}
    
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if data.get("api_key"):
            data["api_key"] = decrypt_value(data["api_key"])
        return data
    except Exception:
        return {}


def save_config(provider_name: str, api_key: str, model_name: str) -> None:
    
    data = {
        "provider": provider_name,
        "api_key": encrypt_value(api_key),
        "model": model_name,
    }
    CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    CONFIG_PATH.chmod(0o600)


def reset_config() -> None:
    
    CONFIG_PATH.unlink(missing_ok=True)
    SECRET_PATH.unlink(missing_ok=True)