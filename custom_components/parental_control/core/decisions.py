"""Décisions du parent et usage, persistables (pur, sans homeassistant)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass(frozen=True)
class Target:
    resource_id: str | None = None
    kid_id: str | None = None
    service: str | None = None


@dataclass(frozen=True)
class ManualException:
    id: str
    target: Target
    open: bool
    created: datetime
    until: datetime | None
    signature: tuple | None


@dataclass(frozen=True)
class Timer:
    kid_id: str
    start: datetime
    end: datetime


@dataclass(frozen=True)
class Bonus:
    day: date
    minutes: int
    kid_id: str | None = None
    resource_id: str | None = None


def _sig_to_json(sig: Any) -> Any:
    if isinstance(sig, tuple):
        return [_sig_to_json(s) for s in sig]
    return sig


def _sig_from_json(sig: Any) -> Any:
    if isinstance(sig, list):
        return tuple(_sig_from_json(s) for s in sig)
    return sig


@dataclass
class Decisions:
    homework_done: dict[str, date] = field(default_factory=dict)
    bonuses: list[Bonus] = field(default_factory=list)
    exceptions: list[ManualException] = field(default_factory=list)
    timers: list[Timer] = field(default_factory=list)
    paused: bool = False
    resource_usage: dict[tuple[str, date], float] = field(default_factory=dict)

    def homework_done_on(self, kid_id: str, day: date) -> bool:
        return self.homework_done.get(kid_id) == day

    def bonus_minutes(
        self, day: date, *, kid_id: str | None = None, resource_id: str | None = None
    ) -> int:
        return sum(
            b.minutes
            for b in self.bonuses
            if b.day == day and b.kid_id == kid_id and b.resource_id == resource_id
        )

    def active_timer(self, kid_id: str, now: datetime) -> Timer | None:
        for t in self.timers:
            if t.kid_id == kid_id and t.start <= now < t.end:
                return t
        return None

    def kid_timer_minutes(self, kid_id: str, day: date, now: datetime) -> float:
        total = 0.0
        for t in self.timers:
            if t.kid_id != kid_id or t.start.date() != day:
                continue
            elapsed = (min(now, t.end) - t.start).total_seconds() / 60
            total += max(elapsed, 0.0)
        return total

    def add_usage(self, resource_id: str, day: date, minutes: float) -> None:
        key = (resource_id, day)
        self.resource_usage[key] = self.resource_usage.get(key, 0.0) + minutes

    def usage(self, resource_id: str, day: date) -> float:
        return self.resource_usage.get((resource_id, day), 0.0)

    def purge(self, now: datetime) -> None:
        today = now.date()
        self.homework_done = {k: d for k, d in self.homework_done.items() if d >= today}
        self.bonuses = [b for b in self.bonuses if b.day >= today]
        self.resource_usage = {k: v for k, v in self.resource_usage.items() if k[1] >= today}
        self.timers = [t for t in self.timers if t.end.date() >= today]
        self.exceptions = [e for e in self.exceptions if e.until is None or e.until > now]

    def prune_unknown(self, kid_ids: set[str], resource_ids: set[str]) -> int:
        """Retire les décisions visant un enfant ou une ressource absents de la config ;
        renvoie le nombre d'entrées retirées."""

        def known(kid_id: str | None, resource_id: str | None) -> bool:
            return ((kid_id is None or kid_id in kid_ids)
                    and (resource_id is None or resource_id in resource_ids))

        before = (len(self.homework_done) + len(self.bonuses) + len(self.timers)
                  + len(self.exceptions))
        self.homework_done = {k: d for k, d in self.homework_done.items() if k in kid_ids}
        self.bonuses = [b for b in self.bonuses if known(b.kid_id, b.resource_id)]
        self.timers = [t for t in self.timers if t.kid_id in kid_ids]
        self.exceptions = [e for e in self.exceptions
                           if known(e.target.kid_id, e.target.resource_id)]
        return before - (len(self.homework_done) + len(self.bonuses) + len(self.timers)
                         + len(self.exceptions))

    def to_dict(self) -> dict:
        return {
            "homework_done": {k: d.isoformat() for k, d in self.homework_done.items()},
            "bonuses": [
                {"day": b.day.isoformat(), "minutes": b.minutes,
                 "kid_id": b.kid_id, "resource_id": b.resource_id}
                for b in self.bonuses
            ],
            "exceptions": [
                {
                    "id": e.id,
                    "target": {"resource_id": e.target.resource_id,
                               "kid_id": e.target.kid_id, "service": e.target.service},
                    "open": e.open,
                    "created": e.created.isoformat(),
                    "until": e.until.isoformat() if e.until else None,
                    "signature": _sig_to_json(e.signature),
                }
                for e in self.exceptions
            ],
            "timers": [
                {"kid_id": t.kid_id, "start": t.start.isoformat(), "end": t.end.isoformat()}
                for t in self.timers
            ],
            "paused": self.paused,
            "resource_usage": [
                {"resource_id": r, "day": d.isoformat(), "minutes": m}
                for (r, d), m in self.resource_usage.items()
            ],
        }

    @classmethod
    def from_dict(cls, d: dict) -> Decisions:
        return cls(
            homework_done={k: date.fromisoformat(v) for k, v in d.get("homework_done", {}).items()},
            bonuses=[
                Bonus(date.fromisoformat(b["day"]), b["minutes"],
                      b.get("kid_id"), b.get("resource_id"))
                for b in d.get("bonuses", [])
            ],
            exceptions=[
                ManualException(
                    id=e["id"],
                    target=Target(**e["target"]),
                    open=e["open"],
                    created=datetime.fromisoformat(e["created"]),
                    until=datetime.fromisoformat(e["until"]) if e.get("until") else None,
                    signature=_sig_from_json(e.get("signature")),
                )
                for e in d.get("exceptions", [])
            ],
            timers=[
                Timer(t["kid_id"], datetime.fromisoformat(t["start"]),
                      datetime.fromisoformat(t["end"]))
                for t in d.get("timers", [])
            ],
            paused=d.get("paused", False),
            resource_usage={
                (u["resource_id"], date.fromisoformat(u["day"])): u["minutes"]
                for u in d.get("resource_usage", [])
            },
        )
