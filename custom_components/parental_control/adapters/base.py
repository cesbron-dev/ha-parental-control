"""Contrat commun des adaptateurs de ressources."""

from __future__ import annotations

from typing import Protocol

from ..core.evaluator import ResourceState
from ..core.model import Resource


class Adapter(Protocol):
    """Traduit l'état voulu d'une ressource en appels de services HA."""

    resource: Resource

    def entity_ids(self) -> list[str]:
        """Entités à écouter pour détecter une dérive."""
        ...

    def in_use(self) -> bool:
        """Ressource en cours d'utilisation (décompte d'usage) ; False si non mesurable."""
        ...

    def drifted(self, desired: ResourceState) -> bool:
        """L'état réel contredit l'état fermé (ou bloqué) attendu."""
        ...

    async def apply(self, desired: ResourceState) -> None:
        """Amène l'appareil dans l'état voulu."""
        ...

    async def warn(self, message: str) -> None:
        """Avertit sur l'appareil lui-même, si possible."""
        ...

    async def grant(self, minutes: int) -> None:
        """Accorde du temps sur l'appareil (Nintendo seulement)."""
        ...

    async def force_close(self) -> None:
        """Ferme immédiatement (pause)."""
        ...
