"""
Encryption Service for WooCommerce Consumer Keys.

Uses Fernet symmetric encryption to securely store WooCommerce API credentials
(Consumer Key and Consumer Secret) in the database.

The encryption key is derived from the application's SECRET_KEY to avoid
storing a separate key. In production, use a dedicated encryption key
environment variable (CONSUMER_KEY_ENCRYPTION_KEY).
"""

import base64
import hashlib
import os
import logging
from typing import Optional

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.config import settings

logger = logging.getLogger(__name__)


def _get_encryption_key() -> bytes:
    """
    Derive a Fernet-compatible encryption key from the application secret.

    Uses PBKDF2 with a fixed salt to derive a 32-byte key from SECRET_KEY.
    This ensures deterministic key derivation without needing a separate
    environment variable.

    In production, set CONSUMER_KEY_ENCRYPTION_KEY environment variable
    (a base64-encoded 32-byte Fernet key) for additional security isolation.
    """
    # Allow override via dedicated env var
    dedicated_key = os.environ.get("CONSUMER_KEY_ENCRYPTION_KEY", "")
    if dedicated_key:
        try:
            # Treat as a raw Fernet key (base64-encoded 32 bytes)
            return dedicated_key.encode()
        except Exception:
            pass

    # Derive from SECRET_KEY using PBKDF2
    secret = settings.SECRET_KEY
    salt = b"digital_fte_wc_key_encryption_v1"
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(secret.encode()))
    return key


def encrypt_value(plaintext: str) -> str:
    """
    Encrypt a string value (Consumer Key or Secret).

    Args:
        plaintext: The plain text string to encrypt

    Returns:
        Base64-encoded encrypted string
    """
    if not plaintext:
        return ""
    try:
        key = _get_encryption_key()
        f = Fernet(key)
        encrypted = f.encrypt(plaintext.encode())
        return encrypted.decode()
    except Exception as exc:
        logger.error("Encryption failed: %s", exc)
        raise


def decrypt_value(encrypted_text: str) -> str:
    """
    Decrypt a previously encrypted string value.

    Args:
        encrypted_text: The encrypted string (Fernet token)

    Returns:
        Decrypted plain text string
    """
    if not encrypted_text:
        return ""
    try:
        key = _get_encryption_key()
        f = Fernet(key)
        decrypted = f.decrypt(encrypted_text.encode())
        return decrypted.decode()
    except Exception as exc:
        logger.error("Decryption failed: %s", exc)
        raise


def encrypt_store_credentials(
    consumer_key: str,
    consumer_secret: str,
) -> tuple[str, str]:
    """
    Encrypt both Consumer Key and Consumer Secret.

    Args:
        consumer_key: Plain text Consumer Key
        consumer_secret: Plain text Consumer Secret

    Returns:
        Tuple of (encrypted_consumer_key, encrypted_consumer_secret)
    """
    return encrypt_value(consumer_key), encrypt_value(consumer_secret)


def decrypt_store_credentials(
    encrypted_key: str,
    encrypted_secret: str,
) -> tuple[str, str]:
    """
    Decrypt both Consumer Key and Consumer Secret.

    Args:
        encrypted_key: Encrypted Consumer Key
        encrypted_secret: Encrypted Consumer Secret

    Returns:
        Tuple of (decrypted_consumer_key, decrypted_consumer_secret)
    """
    return decrypt_value(encrypted_key), decrypt_value(encrypted_secret)


def mask_credential(credential: str) -> str:
    """
    Mask a credential for logging purposes.
    Shows only the first 4 and last 4 characters.

    Example: "ck_abc123def456" -> "ck_a****456"
    """
    if not credential or len(credential) < 8:
        return "****"
    return credential[:4] + "****" + credential[-4:]
