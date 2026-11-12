"""Textes du serveur en anglais et en français (pur, sans homeassistant).

La langue vient de l'appelant (`hass.config.language`, lue dans la couche HA) ; une langue
régionale se ramène à sa langue de base, une langue sans catalogue à l'anglais. Les gabarits
utilisent `str.format`. Les messages `config.<code>` sont ceux de `ConfigError` ; ils sont
repris, précédés de `{path}`, dans la section `exceptions` des traductions (`config_<code>`).
"""

from __future__ import annotations

DEFAULT_LANGUAGE = "en"

MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        "notify.title": "Parental control",
        "panel.rules": "Rules",
        "invalid_config.message": "Parental control: invalid configuration, engine inactive",
        # Simulation : préfixe des notifications, lignes du journal de bord.
        "simulation.prefix": "[Simulation] ",
        "simulation.line": "Simulation: {line}",
        "simulation.switch": "{name}: {action} ({effect} {service})",
        "simulation.turn_on": "turn on",
        "simulation.turn_off": "turn off",
        "simulation.block": "block",
        "simulation.allow": "allow",
        "simulation.switch_off": "would turn off {label}",
        "simulation.switch_on": "would turn {label} back on",
        "simulation.adguard_block": "would block {services} on {label}",
        "simulation.adguard_unblock": "would unblock {services} on {label}",
        "simulation.media_off": "would turn off {label}",
        "simulation.media_warn": "would show “{message}” on {label}",
        "simulation.nintendo_reset": "would reset the limit of {label} to 0 min",
        "simulation.nintendo_grant": "would grant {minutes} min on {label}",
        # Avertissements avant fermeture.
        "warn.kid": "{name}: screens end in {minutes} min",
        "warn.service": "{service} on {resource}: cut-off in {minutes} min",
        "warn.resource": "{resource}: cut-off in {minutes} min",
        # Durées.
        "duration.minutes": "{minutes} min",
        "duration.hours": "{hours} h",
        "duration.hours_minutes": "{hours} h {minutes} min",
        "duration.until_next_change": "Until the next change",
        # Raisons de l'évaluateur (`reason_code`, `reason_params`).
        "reason.allowed_until": "Screens allowed until {until}",
        "reason.allowed_until_midnight": "Screens allowed until midnight",
        "reason.open_for": "Open for {names}",
        "reason.waiting_homework": "Homework to finish",
        "reason.quota_exhausted": "Quota exhausted",
        "reason.waiting_timer": "Waiting for the timer",
        "reason.on_demand": "On demand",
        "reason.blocked": "Blocked",
        "reason.paused": "Screens paused",
        "reason.opened_manually": "Opened manually",
        "reason.closed_manually": "Closed manually",
        # Demandes : message aux parents, boutons, raisons d'échec.
        "request.homework": "{kid} says their homework is done",
        "request.bonus": "{kid} asks for a {duration} bonus",
        "request.bonus_on": "{kid} asks for a {duration} bonus on {resource}",
        "request.timer": "{kid} asks for a {duration} timer",
        "request.open.duration": "{kid} asks for {duration}",
        "request.open.duration_resource": "{kid} asks for {duration} on {resource}",
        "request.open.duration_service": "{kid} asks for {duration} of {service}",
        "request.open.duration_service_resource":
            "{kid} asks for {duration} of {service} on {resource}",
        "request.open.until": "{kid} asks until the next change",
        "request.open.resource_until": "{kid} asks for {resource} until the next change",
        "request.open.service_until": "{kid} asks for {service} until the next change",
        "request.open.service_resource_until":
            "{kid} asks for {service} on {resource} until the next change",
        "request.accept": "Accept",
        "request.accept_duration": "Accept {duration}",
        "request.accept_until": "Accept until the next change",
        "request.refuse": "Refuse",
        "request.reason.impossible": "Action not possible",
        "request.reason.unknown_choice": "Unknown choice",
        # Journal de bord des demandes.
        "log.refused": "Request from {kid} refused by {parent}",
        "log.failed": "Request from {kid} accepted by {parent}, but not possible: {reason}",
        "log.accepted": "Request from {kid} accepted by {parent}",
        "log.accepted_duration": "Request from {kid} accepted by {parent}: {duration}",
        "log.accepted_until": "Request from {kid} accepted by {parent}: until the next change",
        "log.expired": "Request from {kid} unanswered",
        # Erreurs de configuration (`ConfigError`), sans le chemin.
        "config.object_expected": "object expected",
        "config.list_expected": "list expected",
        "config.text_expected": "non-empty text expected",
        "config.integer_expected": "non-negative integer expected",
        "config.boolean_expected": "boolean expected",
        "config.unknown_value": "unknown value {value} (expected: {expected})",
        "config.invalid_time": "invalid time {value} (format HH:MM)",
        "config.segment_required": "at least one segment is required",
        "config.first_segment_midnight": "the first segment must start at 00:00",
        "config.segments_not_increasing": "start times must be strictly increasing",
        "config.profile_required": "the “{profile}” profile is required",
        "config.switch_entity_expected": "switch.* entity expected",
        "config.integration_required": "at least one integration",
        "config.nintendo_alone": "a Nintendo console cannot be grouped",
        "config.duplicate_id": "duplicate identifier: {id}",
        "config.duplicate_label": "duplicate label: {label}",
        "config.label_already_attached": "label {label} already attached to service {service}",
        "config.label_is_target": "label {label} is also the target label of {target}",
        "config.target_label_used": "target label already used: {label}",
        "config.unknown_service": "unknown service: {service}",
        "config.unknown_kid": "unknown child: {kid}",
        "config.unknown_resource": "unknown resource: {resource}",
        "config.unsupported_version": "unsupported version: {version}",
        "config.not_in_request_notify": "target missing from request_notify",
        "config.phone_not_found": "{target}: device not found or ambiguous",
    },
    "fr": {
        "notify.title": "Contrôle parental",
        "panel.rules": "Règles",
        "invalid_config.message": "Contrôle parental : configuration invalide, moteur inactif",
        "simulation.prefix": "[Simulation] ",
        "simulation.line": "Simulation : {line}",
        "simulation.switch": "{name} : {action} ({effect} {service})",
        "simulation.turn_on": "allumer",
        "simulation.turn_off": "éteindre",
        "simulation.block": "bloquer",
        "simulation.allow": "autoriser",
        "simulation.switch_off": "couperait {label}",
        "simulation.switch_on": "rallumerait {label}",
        "simulation.adguard_block": "bloquerait {services} sur {label}",
        "simulation.adguard_unblock": "débloquerait {services} sur {label}",
        "simulation.media_off": "éteindrait {label}",
        "simulation.media_warn": "afficherait « {message} » sur {label}",
        "simulation.nintendo_reset": "remettrait la limite de {label} à 0 min",
        "simulation.nintendo_grant": "accorderait {minutes} min sur {label}",
        "warn.kid": "{name} : fin des écrans dans {minutes} min",
        "warn.service": "{service} sur {resource} : coupure dans {minutes} min",
        "warn.resource": "{resource} : coupure dans {minutes} min",
        "duration.minutes": "{minutes} min",
        "duration.hours": "{hours} h",
        "duration.hours_minutes": "{hours} h {minutes:02d}",
        "duration.until_next_change": "Jusqu'au prochain changement",
        "reason.allowed_until": "Écrans autorisés jusqu'à {until}",
        "reason.allowed_until_midnight": "Écrans autorisés jusqu'à minuit",
        "reason.open_for": "Ouverte pour {names}",
        "reason.waiting_homework": "Devoirs à terminer",
        "reason.quota_exhausted": "Quota épuisé",
        "reason.waiting_timer": "En attente du minuteur",
        "reason.on_demand": "Sur demande",
        "reason.blocked": "Bloqué",
        "reason.paused": "Écrans en pause",
        "reason.opened_manually": "Ouverte manuellement",
        "reason.closed_manually": "Fermée manuellement",
        "request.homework": "{kid} dit avoir terminé ses devoirs",
        "request.bonus": "{kid} demande un bonus de {duration}",
        "request.bonus_on": "{kid} demande un bonus de {duration} sur {resource}",
        "request.timer": "{kid} demande un minuteur de {duration}",
        "request.open.duration": "{kid} demande {duration}",
        "request.open.duration_resource": "{kid} demande {duration} sur {resource}",
        "request.open.duration_service": "{kid} demande {duration} de {service}",
        "request.open.duration_service_resource":
            "{kid} demande {duration} de {service} sur {resource}",
        "request.open.until": "{kid} demande jusqu'au prochain changement",
        "request.open.resource_until": "{kid} demande {resource} jusqu'au prochain changement",
        "request.open.service_until": "{kid} demande {service} jusqu'au prochain changement",
        "request.open.service_resource_until":
            "{kid} demande {service} sur {resource} jusqu'au prochain changement",
        "request.accept": "Accepter",
        "request.accept_duration": "Accepter {duration}",
        "request.accept_until": "Accepter jusqu'au prochain changement",
        "request.refuse": "Refuser",
        "request.reason.impossible": "Action impossible",
        "request.reason.unknown_choice": "Choix inconnu",
        "log.refused": "Demande de {kid} refusée par {parent}",
        "log.failed": "Demande de {kid} acceptée par {parent}, mais impossible : {reason}",
        "log.accepted": "Demande de {kid} acceptée par {parent}",
        "log.accepted_duration": "Demande de {kid} acceptée par {parent} : {duration}",
        "log.accepted_until":
            "Demande de {kid} acceptée par {parent} : jusqu'au prochain changement",
        "log.expired": "Demande de {kid} sans réponse",
        "config.object_expected": "objet attendu",
        "config.list_expected": "liste attendue",
        "config.text_expected": "texte non vide attendu",
        "config.integer_expected": "entier positif ou nul attendu",
        "config.boolean_expected": "booléen attendu",
        "config.unknown_value": "valeur inconnue {value} (attendu : {expected})",
        "config.invalid_time": "heure invalide {value} (format HH:MM)",
        "config.segment_required": "au moins un segment est requis",
        "config.first_segment_midnight": "le premier segment doit commencer à 00:00",
        "config.segments_not_increasing": "les heures de début doivent être strictement croissantes",
        "config.profile_required": "le profil « {profile} » est requis",
        "config.switch_entity_expected": "entité switch.* attendue",
        "config.integration_required": "au moins une intégration",
        "config.nintendo_alone": "une console Nintendo ne se regroupe pas",
        "config.duplicate_id": "identifiant en double : {id}",
        "config.duplicate_label": "label en double : {label}",
        "config.label_already_attached": "label {label} déjà rattaché au service {service}",
        "config.label_is_target": "le label {label} est aussi le label de cible de {target}",
        "config.target_label_used": "label de cible déjà utilisé : {label}",
        "config.unknown_service": "service inconnu : {service}",
        "config.unknown_kid": "enfant inconnu : {kid}",
        "config.unknown_resource": "ressource inconnue : {resource}",
        "config.unsupported_version": "version non prise en charge : {version}",
        "config.not_in_request_notify": "cible absente de request_notify",
        "config.phone_not_found": "{target} — appareil introuvable ou en double",
    },
}


def base_language(lang: str | None) -> str:
    """`en` ou `fr` : langue de base de `lang` (`fr-CA` → `fr`), `en` sans catalogue."""
    if not lang:
        return DEFAULT_LANGUAGE
    base = lang.replace("_", "-").split("-", 1)[0].lower()
    return base if base in MESSAGES else DEFAULT_LANGUAGE


def msg(lang: str | None, key: str, **params: object) -> str:
    """Texte `key` dans la langue `lang`, repli sur l'anglais puis sur la clé elle-même."""
    template = MESSAGES[base_language(lang)].get(key) or MESSAGES[DEFAULT_LANGUAGE].get(key)
    if template is None:
        return key
    return template.format(**params) if params else template


def duration_text(lang: str | None, minutes: int | None) -> str:
    """Durée lisible (en : « 1 h 30 min », fr : « 1 h 30 ») ; `None` = jusqu'au prochain
    changement."""
    if minutes is None:
        return msg(lang, "duration.until_next_change")
    hours, mins = divmod(minutes, 60)
    if hours == 0:
        return msg(lang, "duration.minutes", minutes=mins)
    if mins == 0:
        return msg(lang, "duration.hours", hours=hours)
    return msg(lang, "duration.hours_minutes", hours=hours, minutes=mins)
