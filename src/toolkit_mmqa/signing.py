"""Ed25519 signing and verification for scan results."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class KeyPair:
    """Ed25519 key pair."""

    private_key_pem: str
    public_key_pem: str


def _ensure_cryptography() -> None:
    """Check that the cryptography package is available."""
    try:
        import cryptography  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "The 'cryptography' package is required for signing. "
            "Install it with: pip install cryptography"
        ) from exc


def generate_ed25519_keypair() -> KeyPair:
    """Generate a new Ed25519 key pair.

    Returns:
        KeyPair with PEM-encoded private and public keys.

    Raises:
        RuntimeError: If cryptography package is not installed.
    """
    _ensure_cryptography()
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519

    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return KeyPair(private_key_pem=private_pem, public_key_pem=public_pem)


def canonical_json_bytes(obj: Any) -> bytes:
    """Deterministic JSON serialization for signing.

    Uses sorted keys and compact separators to ensure
    identical payloads produce identical bytes.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def sign_payload(*, payload: bytes, private_key_pem: str) -> str:
    """Sign bytes with an Ed25519 private key.

    Args:
        payload: Bytes to sign.
        private_key_pem: PEM-encoded Ed25519 private key.

    Returns:
        Base64-encoded signature string.

    Raises:
        RuntimeError: If cryptography package is not installed.
        ValueError: If key is not Ed25519.
    """
    _ensure_cryptography()
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    private_key = serialization.load_pem_private_key(private_key_pem.encode("utf-8"), password=None)
    if not isinstance(private_key, Ed25519PrivateKey):
        raise ValueError("Key is not an Ed25519 private key")
    sig = private_key.sign(payload)
    return base64.b64encode(sig).decode("ascii")


def verify_payload(*, payload: bytes, signature_b64: str, public_key_pem: str) -> bool:
    """Verify an Ed25519 signature.

    Args:
        payload: Original bytes that were signed.
        signature_b64: Base64-encoded signature.
        public_key_pem: PEM-encoded Ed25519 public key.

    Returns:
        True if signature is valid, False otherwise.

    Raises:
        RuntimeError: If cryptography package is not installed.
        ValueError: If key is not Ed25519.
    """
    _ensure_cryptography()
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    public_key = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))
    if not isinstance(public_key, Ed25519PublicKey):
        raise ValueError("Key is not an Ed25519 public key")
    try:
        public_key.verify(base64.b64decode(signature_b64.encode("ascii")), payload)
        return True
    except Exception:
        return False
