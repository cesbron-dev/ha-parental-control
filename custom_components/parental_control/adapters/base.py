"""Contrat commun des adaptateurs d'intégration (membres d'un `CompositeAdapter`)."""

from __future__ import annotations

from typing import Protocol

from ..core.evaluator import ResourceState


class Adapter(Protocol):
    """Traduit l'état voulu d'une ressource en appels de services HA, pour une intégration."""

    label: str  # « <appareil physique> (<entity_id>) » pour un lecteur, l'appareil sinon

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

    def describe(self, desired: ResourceState) -> list[str]:
        """Ce que `apply(desired)` ferait maintenant, sans rien appeler ; [] si rien.

        Appelé à la place d'`apply` (simulation), une fois par application : un adaptateur qui
        retient le dernier état voulu (interrupteur) le met à jour ici aussi."""
        ...

    def describe_grant(self, minutes: int) -> list[str]:
        """Ce que `grant(minutes)` ferait (Nintendo seulement) ; [] sinon."""
        ...

    def describe_warn(self, message: str) -> list[str]:
        """Ce que `warn(message)` ferait ; [] si l'appareil ne sait pas avertir."""
        ...

    def pause_state(self) -> ResourceState:
        """État fermé appliqué par `force_close` (la pause)."""
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
