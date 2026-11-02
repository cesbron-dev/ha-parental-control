"""Appareil client `adguard_clients` simulé : capteur « Services bloqués » + écriture."""

from __future__ import annotations

from collections.abc import Iterable

from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import slugify
from pytest_homeassistant_custom_component.common import MockConfigEntry

DOMAIN = "adguard_clients"
_FAKES = "test_fake_adguard_clients"


class FakeAdGuard:
    """Le capteur n'a pas d'état tant que `set_blocked` n'a pas été appelé.

    Plusieurs instances peuvent coexister : le service partagé route chaque écriture
    vers l'appareil de son `device_id`.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        calls: list[ServiceCall] | None = None,
        name: str = "iPhone Hugo",
    ) -> None:
        self.hass = hass
        # liste partageable avec d'autres services simulés (ordre global des appels)
        self.calls: list[ServiceCall] = [] if calls is None else calls
        self.error: Exception | None = None
        self.use_global = False
        entry = MockConfigEntry(domain=DOMAIN)
        entry.add_to_hass(hass)
        device = dr.async_get(hass).async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, f"{entry.entry_id}_uid1")},
            name=name,
        )
        self.device_id = device.id
        self.entity_id = (
            er.async_get(hass)
            .async_get_or_create(
                "sensor",
                DOMAIN,
                f"{entry.entry_id}_uid1_blocked_services",
                config_entry=entry,
                device_id=device.id,
                suggested_object_id=f"{slugify(name)}_services_bloques",
            )
            .entity_id
        )
        hass.data.setdefault(_FAKES, {})[self.device_id] = self
        self.register()

    def register(self) -> None:
        fakes = self.hass.data[_FAKES]

        async def set_blocked_services(call: ServiceCall) -> dict:
            return await fakes[call.data["device_id"]].handle(call)

        self.hass.services.async_register(
            DOMAIN,
            "set_blocked_services",
            set_blocked_services,
            supports_response=SupportsResponse.OPTIONAL,
        )

    def set_blocked(self, services: Iterable[str]) -> None:
        services = sorted(services)
        self.hass.states.async_set(
            self.entity_id,
            str(len(services)),
            {"services": services, "use_global_blocked_services": self.use_global},
        )

    @property
    def blocked(self) -> list[str]:
        state = self.hass.states.get(self.entity_id)
        return [] if state is None else list(state.attributes["services"])

    def blocks(self) -> list[str]:
        """Services bloqués par les écritures reçues (toutes confondues)."""
        return sorted(s for c in self._own_calls() for s in c.data["block"])

    def unblocks(self) -> list[str]:
        return sorted(s for c in self._own_calls() for s in c.data["unblock"])

    def _own_calls(self) -> list[ServiceCall]:
        return [
            c for c in self.calls
            if c.domain == DOMAIN and c.data["device_id"] == self.device_id
        ]

    async def handle(self, call: ServiceCall) -> dict:
        self.calls.append(call)
        if self.error is not None:
            raise self.error
        new = (set(self.blocked) | set(call.data.get("block", []))) - set(
            call.data.get("unblock", [])
        )
        self.set_blocked(new)
        return {"blocked_services": sorted(new)}
