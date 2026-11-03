"""Adaptateur composite : un appareil logique, un membre par intégration."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from ..core.evaluator import ResourceState
from ..core.model import Resource
from .base import Adapter
from .nintendo import NintendoAdapter

_LOGGER = logging.getLogger(__name__)

_WARN = "l'avertissement"


class CompositeAdapter:
    """Le moteur ne voit que lui. Chaque écriture passe à tous les membres, isolément :
    l'échec d'un membre est journalisé avec son label et n'empêche pas les autres
    (un membre absent de HA est déjà ignoré, et signalé une fois, par son adaptateur).
    """

    def __init__(self, resource: Resource, members: list[Adapter]) -> None:
        self.resource = resource
        self.members = members

    @property
    def nintendo(self) -> NintendoAdapter | None:
        """Membre Nintendo (bonus de temps, capteurs d'usage) ; None s'il n'y en a pas."""
        for member in self.members:
            if isinstance(member, NintendoAdapter):
                return member
        return None

    # Lecture

    def entity_ids(self) -> list[str]:
        return list(dict.fromkeys(e for m in self.members for e in m.entity_ids()))

    def in_use(self) -> bool:
        # seuls les lecteurs et les interrupteurs savent dire s'ils sont utilisés
        return any(m.in_use() for m in self.members)

    def drifted(self, desired: ResourceState) -> bool:
        return any(m.drifted(desired) for m in self.members)

    def describe(self, desired: ResourceState) -> list[str]:
        return [line for m in self.members for line in m.describe(desired)]

    def describe_pause(self) -> list[str]:
        """Ce que `force_close` ferait : chaque membre avec son propre état de pause."""
        return [line for m in self.members for line in m.describe(m.pause_state())]

    def describe_grant(self, minutes: int) -> list[str]:
        nintendo = self.nintendo
        return [] if nintendo is None else nintendo.describe_grant(minutes)

    def describe_warn(self, message: str) -> list[str]:
        return [line for m in self.members for line in m.describe_warn(message)]

    # Écriture

    async def _each(self, action: str, call: Callable[[Adapter], Awaitable[None]]) -> None:
        for member in self.members:
            try:
                await call(member)
            except Exception as err:  # noqa: BLE001 - un membre n'arrête pas les autres
                # un avertissement manqué n'est pas une panne (comme avant le composite)
                level = logging.WARNING if action == _WARN else logging.ERROR
                _LOGGER.log(level, "%s : échec de %s : %s", member.label, action, err)

    async def apply(self, desired: ResourceState) -> None:
        await self._each("l'application", lambda m: m.apply(desired))

    async def warn(self, message: str) -> None:
        await self._each(_WARN, lambda m: m.warn(message))

    async def force_close(self) -> None:
        await self._each("la pause", lambda m: m.force_close())

    async def grant(self, minutes: int) -> None:
        nintendo = self.nintendo
        if nintendo is None:
            raise NotImplementedError
        await nintendo.grant(minutes)
