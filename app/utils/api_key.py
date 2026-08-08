import secrets
import string

BASE62_ALPHABET = string.ascii_letters + string.digits


def generate_api_key(is_live: bool = True) -> str:
    """
    Generate a secure API key.
    Formatted as: twf_{env_tag live/test}_{identifier 8 chars}_{secure_secret 32 chars}

    Args:
        is_live (bool): Flag to indicate if the key is for live or test environment.

    Returns:
        str: A securely generated API key.
    """
    env_tag = "live" if is_live else "test"
    identifier = "".join(secrets.choice(BASE62_ALPHABET) for _ in range(8))
    secure_secret = "".join(secrets.choice(BASE62_ALPHABET) for _ in range(32))

    return f"twf_{env_tag}_{identifier}_{secure_secret}"
