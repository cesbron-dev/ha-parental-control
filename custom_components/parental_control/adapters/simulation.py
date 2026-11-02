"""Enveloppe de simulation : calcule et journalise sans toucher à l'appareil."""

from __future__ import annotations

from collections.abc import Callable

from ..core.evaluator import ResourceState
from ..core.model import Resource
from .base import Adapter


class SimulatedAdapter:
    """Même contrat qu'`Adapter`. Hors simulation, tout passe à `inner` ; en simulation,
    `apply`/`force_close`/`grant`/`warn` décrivent leur effet via `record(nom, ligne)`.

    Une ligne déjà enregistrée par l'appel précédent n'est pas répétée (une dérive
    persistante ne remplit pas le journal) ; `reset()` oublie cette mémoire.
    """

    def __init__(
        self,
        inner: Adapter,
        active: Callable[[], bool],
        record: Callable[[str, str], None],
    ) -> None:
        self.inner = inner
        self._active = active
        self._record = record
        self._last: set[str] = set()

    @property
    def resource(self) -> Resource:
        return self.inner.resource

    def reset(self) -> None:
        self._last = set()

    def _log(self, lines: list[str]) -> None:
        if not lines:
            return
        for line in lines:
            if line not in self._last:
                self._record(self.resource.name, line)
        self._last = set(lines)

    # Lecture : toujours sur l'appareil réel.

    def entity_ids(self) -> list[str]:
        return self.inner.entity_ids()

    def in_use(self) -> bool:
        return self.inner.in_use()

    def drifted(self, desired: ResourceState) -> bool:
        return self.inner.drifted(desired)

    def describe(self, desired: ResourceState) -> list[str]:
        return self.inner.describe(desired)

    def describe_grant(self, minutes: int) -> list[str]:
        return self.inner.describe_grant(minutes)

    def pause_state(self) -> ResourceState:
        return self.inner.pause_state()

    # Écriture : décrite en simulation, déléguée sinon.

    async def apply(self, desired: ResourceState) -> None:
        if not self._active():
            await self.inner.apply(desired)
            return
        self._log(self.inner.describe(desired))

    async def force_close(self) -> None:
        if not self._active():
            await self.inner.force_close()
            return
        self._log(self.inner.describe(self.inner.pause_state()))

    async def grant(self, minutes: int) -> None:
        if not self._active():
            await self.inner.grant(minutes)
            return
        self._log(self.inner.describe_grant(minutes))

    async def warn(self, message: str) -> None:
        if not self._active():
            await self.inner.warn(message)
            return
        self._log([f"afficherait « {message} » sur {self.resource.name}"])
