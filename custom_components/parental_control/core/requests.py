"""Cycle de vie des demandes de temps des enfants (pur, sans homeassistant)."""

from __future__ import annotations

import hmac
import secrets
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum

from .i18n import DEFAULT_LANGUAGE, duration_text, msg

REQUEST_TIMEOUT = timedelta(minutes=15)
RESULT_DISPLAY = timedelta(minutes=5)
MAX_OPTIONS = 6
MIN_MINUTES = 1
MAX_MINUTES = 240
MAX_PENDING_PER_KID = 3  # contre l'envoi en rafale vers les téléphones des parents

class RequestKind(StrEnum):
    OPEN = "open"
    BONUS = "bonus"
    HOMEWORK = "homework"
    TIMER = "timer"


class RequestStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REFUSED = "refused"
    EXPIRED = "expired"
    FAILED = "failed"


class RequestError(ValueError):
    """Demande refusée ; `key` est la clé d'erreur traduite côté engine."""

    def __init__(self, key: str) -> None:
        super().__init__(key)
        self.key = key


@dataclass
class TimeRequest:
    id: str
    token: str = field(repr=False)  # secret : jamais dans les journaux
    kind: RequestKind
    kid_id: str
    resource_id: str | None
    service: str | None
    proposed: int | None
    options: tuple[int | None, ...]
    replace: tuple[str, ...]
    created: datetime
    expires: datetime
    status: RequestStatus = RequestStatus.PENDING
    granted: int | None = None
    reason: str | None = None  # texte rendu dans la langue système de HA
    resolved_at: datetime | None = None
    answered_by: str | None = None
    # Raison d'échec indépendante de la langue : `impossible`, `unknown_choice` ou la clé
    # d'erreur de l'action parentale (`not_in_quota`…), avec ses paramètres (textes).
    reason_code: str | None = None
    reason_params: dict[str, str] = field(default_factory=dict)

    @property
    def key(self) -> tuple[str, str, str | None, str | None]:
        return (str(self.kind), self.kid_id, self.resource_id, self.service)


def _check_minutes(value: object) -> None:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not MIN_MINUTES <= value <= MAX_MINUTES
    ):
        raise RequestError("invalid_request")


def normalize_options(
    kind: RequestKind, proposed: int | None, options: Sequence[int | None]
) -> tuple[int | None, ...]:
    """Valide les durées, met `proposed` en tête, sans doublon, borné à MAX_OPTIONS."""
    if kind == RequestKind.HOMEWORK:
        if proposed is not None:
            raise RequestError("invalid_request")
        return ()
    if kind in (RequestKind.BONUS, RequestKind.TIMER) and proposed is None:
        raise RequestError("invalid_request")
    # Toutes les valeurs sont validées avant la coupe à MAX_OPTIONS.
    values = [proposed, *options]
    for value in values:
        if value is None:
            if kind != RequestKind.OPEN:
                raise RequestError("invalid_request")
        else:
            _check_minutes(value)
    result: list[int | None] = []
    for value in values:
        if value not in result:
            result.append(value)
    return tuple(result[:MAX_OPTIONS])


class RequestBook:
    """Registre en mémoire des demandes (en attente ou récemment résolues)."""

    def __init__(self) -> None:
        self._requests: dict[str, TimeRequest] = {}

    def create(
        self,
        kind: RequestKind,
        kid_id: str,
        *,
        resource_id: str | None,
        service: str | None,
        proposed: int | None,
        options: Sequence[int | None],
        replace: Sequence[str],
        now: datetime,
    ) -> TimeRequest:
        opts = normalize_options(kind, proposed, options)
        key = (str(kind), kid_id, resource_id, service)
        pending = [
            r
            for r in self._requests.values()
            if r.status == RequestStatus.PENDING and r.kid_id == kid_id
        ]
        if any(other.key == key for other in pending):
            raise RequestError("request_pending")
        if len(pending) >= MAX_PENDING_PER_KID:
            raise RequestError("too_many_requests")
        req = TimeRequest(
            id=uuid.uuid4().hex,
            token=secrets.token_urlsafe(16),
            kind=kind,
            kid_id=kid_id,
            resource_id=resource_id,
            service=service,
            proposed=proposed,
            options=opts,
            replace=tuple(replace),
            created=now,
            expires=now + REQUEST_TIMEOUT,
        )
        self._requests[req.id] = req
        return req

    def get(self, request_id: str) -> TimeRequest | None:
        return self._requests.get(request_id)

    def claim(self, request_id: str, token: str, now: datetime) -> TimeRequest | None:
        """Réserve la demande pour une seule réponse ; `finish` fixe le statut définitif."""
        req = self._requests.get(request_id)
        if req is None or req.status != RequestStatus.PENDING:
            return None
        if not hmac.compare_digest(req.token.encode(), token.encode()):
            return None
        if now >= req.expires:
            return None
        req.status = RequestStatus.ACCEPTED  # provisoire : bloque une seconde réponse
        return req

    def finish(
        self,
        req: TimeRequest,
        status: RequestStatus,
        now: datetime,
        *,
        granted: int | None = None,
        reason: str | None = None,
        reason_code: str | None = None,
        reason_params: dict[str, str] | None = None,
        answered_by: str | None = None,
    ) -> None:
        req.status = status
        req.granted = granted
        req.reason = reason
        req.reason_code = reason_code
        req.reason_params = dict(reason_params or {})
        req.answered_by = answered_by
        req.resolved_at = now

    def expire(self, now: datetime) -> list[TimeRequest]:
        expired = [
            r
            for r in self._requests.values()
            if r.status == RequestStatus.PENDING and now >= r.expires
        ]
        for req in expired:
            req.status = RequestStatus.EXPIRED
            req.resolved_at = now
        return expired

    def visible(self, now: datetime) -> list[TimeRequest]:
        """Demandes en attente ou résolues récemment ; oublie les plus anciennes."""
        for rid, req in list(self._requests.items()):
            if req.resolved_at is not None and req.resolved_at + RESULT_DISPLAY <= now:
                del self._requests[rid]
        return list(self._requests.values())


def duration_label(minutes: int | None, lang: str = DEFAULT_LANGUAGE) -> str:
    return duration_text(lang, minutes)


def choice_specs(req: TimeRequest) -> list[dict[str, str | int | None]]:
    """Boutons de la demande sans texte : `choice` (réponse), `label` (gabarit `request.<label>`,
    ou `duration` pour la durée seule) et `minutes` (None : jusqu'au prochain changement)."""
    refuse = {"choice": "refuse", "label": "refuse", "minutes": None}
    if req.kind == RequestKind.HOMEWORK:
        return [{"choice": "accept", "label": "accept", "minutes": None}, refuse]
    specs: list[dict[str, str | int | None]] = []
    for i, minutes in enumerate(req.options):
        label = "duration"
        if i == 0 and (req.proposed is not None or minutes is None):
            label = "accept_until" if minutes is None else "accept_duration"
        specs.append({"choice": str(i), "label": label, "minutes": minutes})
    specs.append(refuse)
    return specs


def choice_title(spec: dict[str, str | int | None], lang: str = DEFAULT_LANGUAGE) -> str:
    """Titre d'un bouton de `choice_specs` dans la langue `lang`."""
    minutes = spec["minutes"]
    duration = duration_label(minutes if isinstance(minutes, int) else None, lang)
    if spec["label"] == "duration":
        return duration
    return msg(lang, f"request.{spec['label']}", duration=duration)


def action_choices(req: TimeRequest, lang: str = DEFAULT_LANGUAGE) -> list[tuple[str, str]]:
    """Paires (choix, titre) des boutons de la notification, dans la langue `lang`."""
    return [(str(spec["choice"]), choice_title(spec, lang)) for spec in choice_specs(req)]
