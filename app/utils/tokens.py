import hashlib
import secrets
import string

BASE62_ALPHABET = string.ascii_letters + string.digits
TOKEN_TYPES = ["live", "test", "tunl"]


def generate_secure_token(token_type: str = "live") -> str:
    """
    Generate a secure token string with the specified token type. The token is formatted as follows:
    Formatted as: twf_{token_type 4 chars}_{identifier 8 chars}_{secure_secret 32 chars}

    Args:
        token_type (str): The type of token to generate. It can be "live", "test", or "tunl". Default is "live".

    Returns:
        str: A securely generated token string.
    """
    # 檢查 token_type 是否為有效值
    if token_type not in TOKEN_TYPES:
        raise ValueError(f"Invalid token_type. Must be one of {TOKEN_TYPES}")
    identifier = "".join(secrets.choice(BASE62_ALPHABET) for _ in range(8))
    secure_secret = "".join(secrets.choice(BASE62_ALPHABET) for _ in range(32))

    return f"twf_{token_type}_{identifier}_{secure_secret}"


def hash_session_token(session_token: str) -> str:
    """
    Hash a session token with SHA-256. Redis only stores the hash as the session key,
    so a leaked Redis cannot be used to log in.

    Args:
        session_token (str): The session token stored in the cookie.

    Returns:
        str: The hex digest of the session token.
    """
    return hashlib.sha256(session_token.encode("utf-8")).hexdigest()
