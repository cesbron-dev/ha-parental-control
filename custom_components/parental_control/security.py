"""Code parent : hachage, vérification et contrôle des actions qui débloquent."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass

from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from .const import DOMAIN

_ITERATIONS = 200_000
_PREFIX = "pbkdf2"

MAX_FAILURES = 5
LOCK_SECONDS = 60
MAX_LOCK_SECONDS = 15 * 60
_LOCKOUT_KEY = f"{DOMAIN}_code_lockout"

# Horloge monotone ; remplaçable dans les tests.
_monotonic = time.monotonic


def _derive(code: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", str(code).encode(), salt, _ITERATIONS)


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


@dataclass
class _Attempts:
    failures: int = 0
    locked_until: float = 0.0


class CodeLockout:
    """Verrouillage en mémoire des essais de code, par utilisateur.

    Après `MAX_FAILURES` codes faux consécutifs, les essais sont refusés pendant
    `LOCK_SECONDS` ; chaque échec suivant double le verrou (plafond
    `MAX_LOCK_SECONDS`). Un bon code remet le compteur à zéro. Les vérifications
    sont sérialisées pour qu'une rafale d'appels parallèles ne contourne pas le
    compteur.
    """

    def __init__(self) -> None:
        self._attempts: dict[str, _Attempts] = {}
        self.lock = asyncio.Lock()

    def remaining(self, user_id: str) -> int:
        """Secondes de verrou restantes (0 = pas verrouillé)."""
        attempts = self._attempts.get(user_id)
        if attempts is None:
            return 0
        left = attempts.locked_until - _monotonic()
        return max(0, int(left + 0.999))

    def failure(self, user_id: str) -> None:
        attempts = self._attempts.setdefault(user_id, _Attempts())
        attempts.failures += 1
        extra = attempts.failures - MAX_FAILURES
        if extra >= 0:
            # 2**extra borné pour ne pas fabriquer d'entiers géants.
            seconds = min(LOCK_SECONDS * 2 ** min(extra, 16), MAX_LOCK_SECONDS)
            attempts.locked_until = _monotonic() + seconds

    def success(self, user_id: str) -> None:
        self._attempts.pop(user_id, None)


def _lockout(hass: HomeAssistant) -> CodeLockout:
    lockout = hass.data.get(_LOCKOUT_KEY)
    if lockout is None:
        lockout = hass.data[_LOCKOUT_KEY] = CodeLockout()
    return lockout


def _locked_error(seconds: int) -> ServiceValidationError:
    return ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key="code_locked",
        translation_placeholders={"seconds": str(seconds)},
    )


async def check_unlock(
    hass: HomeAssistant, context: Context, code: str | None, stored_hash: str
) -> None:
    """Autorise une action qui débloque, ou lève `ServiceValidationError`.

    Sans `user_id` (automatisation, système) ou pour un administrateur : pas de code.
    Sinon le code est exigé et vérifié, avec verrouillage après échecs répétés.
    """
    if context.user_id is None:
        return
    user = await hass.auth.async_get_user(context.user_id)
    if user is not None and user.is_admin:
        return
    if code is not None:
        code = str(code)  # un code saisi en YAML peut arriver en entier
    if not code:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="code_required"
        )
    lockout = _lockout(hass)
    user_id = context.user_id
    if seconds := lockout.remaining(user_id):
        raise _locked_error(seconds)
    async with lockout.lock:
        # Re-vérifié sous le verrou : un essai parallèle a pu échouer entre-temps.
        if seconds := lockout.remaining(user_id):
            raise _locked_error(seconds)
        valid = await hass.async_add_executor_job(verify_code, code, stored_hash)
        if valid:
            lockout.success(user_id)
            return
        lockout.failure(user_id)
    raise ServiceValidationError(
        translation_domain=DOMAIN, translation_key="code_invalid"
    )
