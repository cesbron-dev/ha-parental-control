# Carte Switch : bonus en cours — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Afficher « Mise à jour du temps… » sur la carte Switch pendant qu'un bonus est accordé, d'où qu'il vienne.

**Architecture:** Le moteur compte les bonus en cours par ressource autour de `adapter.grant`, prévient les cartes (SIGNAL_UPDATE) au début et à la fin ; le snapshot expose `granting` par ressource ; la carte grise la jauge et désactive les pilules.

**Tech Stack:** Python (HA custom component, pytest-homeassistant), JS vanilla (web components, `node --test`).

**Spec:** `docs/superpowers/specs/2026-11-23-switch-bonus-en-cours-design.md`

## Global Constraints

- Textes fr et en (`www/i18n/fr.js`, `www/i18n/en.js`).
- `granting` lisible sans être admin (même canal que l'état).
- Version 0.6.3 (`manifest.json`).

## Review Focus

- Bonus qui échoue (HomeAssistantError) : l'indicateur doit retomber → test `test_granting_cleared_on_failure`.
- Deux bonus concurrents sur la même Switch : indicateur jusqu'à la fin du dernier → test `test_granting_counts_concurrent_grants`.
- Ressource non Nintendo / bonus enfant : `granting` reste faux → couvert par `test_granting_false_by_default`.
- Ancien backend sans champ `granting` : la carte doit traiter l'absence comme faux → test JS `resourceView granting defaults to false`.

---

### Task 1: Moteur et sérialisation

**Files:**
- Modify: `custom_components/parental_control/engine.py` (`__init__`, `add_bonus`)
- Modify: `custom_components/parental_control/serialize.py` (`serialize_snapshot`)
- Test: `tests/ha/test_engine.py`

**Interfaces:**
- Produces: `ParentalEngine.granting(resource_id: str) -> bool`; clé `granting: bool` dans `serialize_snapshot(...)["resources"][id]`.

- [ ] Tests : `test_granting_false_by_default` (snapshot sérialisé `granting is False`), `test_granting_true_during_grant` (service `add_bonus_time` qui bloque sur un `asyncio.Event` : pendant, `engine.granting("switch")` et `serialize_snapshot` vrais ; après, faux), `test_granting_cleared_on_failure` (le service lève deux fois → `add_bonus` lève, `granting` faux), `test_granting_counts_concurrent_grants`.
- [ ] Vérifier l'échec, implémenter `self._granting: dict[str, int]`, incrément + `async_dispatcher_send(SIGNAL_UPDATE)` avant `grant`, décrément dans `finally` (supprimer la clé à 0) ; la fin est signalée par `async_evaluate`, sinon par dispatch explicite en cas d'échec.
- [ ] `pytest tests/ha/test_engine.py -q` vert, commit.

### Task 2: Carte Switch

**Files:**
- Modify: `www/lib.js` (`resourceView` : `granting: !!r.granting`, défaut `false`)
- Modify: `www/switch-card.js` (classe `.busy`, ligne `card.switch.updating`, pilules `disabled`)
- Modify: `www/style.js` (`bonusPills(hass, minutes, armed, parent, disabled = false)`)
- Modify: `www/i18n/fr.js`, `www/i18n/en.js` : `card.switch.updating` = « Mise à jour du temps… » / "Updating play time…"
- Test: `tests/js/lib.test.mjs`, `tests/js/style.test.mjs`

- [ ] Tests JS : `resourceView granting defaults to false`, `resourceView exposes granting`, `bonusPills disabled` (chaque pilule porte ` disabled`).
- [ ] Implémenter ; CSS : `.busy .arc { opacity: .45; animation: pulse 1.2s ease-in-out infinite }` sous `@media (prefers-reduced-motion: no-preference)` ; `_hassChanged` inchangé (l'état arrive par souscription).
- [ ] `node --test tests/js/*.mjs` vert, commit.

### Task 3: Version et vérification complète

- [ ] `manifest.json` → 0.6.3 ; `pytest -q` et `node --test tests/js/*.mjs` verts ; commit « version 0.6.3 ».
