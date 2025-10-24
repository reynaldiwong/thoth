

from pathlib import Path
from cryptography.fernet import Fernet

SECRET_PATH = Path.home() / ".thoth_secret.key"


def get_fernet() -> Fernet:
    
    if not SECRET_PATH.exists():
        key = Fernet.generate_key()
        SECRET_PATH.write_bytes(key)
        SECRET_PATH.chmod(0o600)
    else:
        key = SECRET_PATH.read_bytes()
    return Fernet(key)


def encrypt_value(plaintext: str) -> str:
    
    return get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    
    try:
        return get_fernet().decrypt(ciphertext.encode()).decode()
    except Exception:
        return ""