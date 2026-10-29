"""Code parent : hachage, vérification et contrôle des actions qui débloquent."""

from __future__ import annotations

import hashlib
import hmac
import secrets

from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from .const import DOMAIN

_ITERATIONS = 200_000
_PREFIX = "pbkdf2"


def _derive(code: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", code.encode(), salt, _ITERATIONS)


def hash_code(code: str) -> str:
    """Hache le code avec un sel aléatoire : `pbkdf2$<sel hex>$<hash hex>`."""
    salt = secrets.token_bytes(16)
    return f"{_PREFIX}${salt.hex()}${_derive(code, salt).hex()}"


def verify_code(code: str, stored: str) -> bool:
    """Compare le code au hachage stocké en temps constant ; format inconnu → False."""
    try:
        prefix, salt_hex, hash_hex = stored.split("$")
        if prefix != _PREFIX:
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except ValueError:
        return False
    return hmac.compare_digest(_derive(code, salt), expected)


async def check_unlock(
    hass: HomeAssistant, context: Context, code: str | None, stored_hash: str
) -> None:
    """Autorise une action qui débloque, ou lève `ServiceValidationError`.

    Sans `user_id` (automatisation, système) ou pour un administrateur : pas de code.
    Sinon le code est exigé et vérifié.
    """
    if context.user_id is None:
        return
    user = await hass.auth.async_get_user(context.user_id)
    if user is not None and user.is_admin:
        return
    if not code:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="code_required"
        )
    if not await hass.async_add_executor_job(verify_code, code, stored_hash):
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="code_invalid"
        )
