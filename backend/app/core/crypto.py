"""Credentials kept in the database are encrypted with Fernet (AES-128-CBC with an HMAC-SHA256
tag), under INTEGRATION_SECRET_KEY from the environment (Milestone 27, ADR 0013 point 7).

The key never enters the database, so a database dump or backup alone does not give the
provider keys away. Make a key with:

    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

import json

from cryptography.fernet import Fernet, InvalidToken


class IntegrationKeyError(RuntimeError):
    """The secret key is missing, malformed, or not the one the credentials were saved with."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


def _fernet(key: str) -> Fernet:
    if not key:
        raise IntegrationKeyError(
            "INTEGRATION_SECRET_KEY is not set, so saved provider keys cannot be used.",
            code="INTEGRATION_KEY_MISSING",
        )
    try:
        return Fernet(key.encode())
    except ValueError as exc:
        raise IntegrationKeyError(
            "INTEGRATION_SECRET_KEY is not a Fernet key (32 bytes, url-safe base64).",
            code="INTEGRATION_KEY_INVALID",
        ) from exc


def check_key(key: str) -> None:
    """A blank key is allowed (no saved credentials); a malformed one is not."""
    if key:
        _fernet(key)


def encrypt_json(data: dict[str, str], key: str) -> str:
    return _fernet(key).encrypt(json.dumps(data, sort_keys=True).encode()).decode()


def decrypt_json(token: str, key: str) -> dict[str, str]:
    try:
        raw = _fernet(key).decrypt(token.encode())
    except InvalidToken as exc:
        raise IntegrationKeyError(
            "The saved provider keys were made with another INTEGRATION_SECRET_KEY.",
            code="INTEGRATION_KEY_MISMATCH",
        ) from exc
    data = json.loads(raw)
    return {str(k): str(v) for k, v in data.items()}
