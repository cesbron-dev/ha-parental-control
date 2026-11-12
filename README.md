# Parental Control for Home Assistant

**English** · [Français](README.fr.md)

A parental control integration for Home Assistant. Each child has a daily timeline for each
type of day (school day, weekend, teacher in-service day, holidays). The engine applies it
continuously to TVs (`media_player`), to AdGuard Home services (through
[ha-adguard-clients](https://github.com/cesbron-dev/ha-adguard-clients)), to third-party
switches and to Nintendo Switch consoles. It also handles homework, quotas, timers, bonuses,
manual exceptions and a global pause.

The project has three parts:

1. **the engine** (this repository): integration, actions, entities, WebSocket API;
2. **the dashboard cards**: see [Cards](#cards);
3. **the « Règles » (Rules) panel**: the visual configuration editor, see
   [Rules panel](#rules-panel).

The configuration can also be loaded as JSON (see below).

Released under the [MIT license](LICENSE).

> **Language.** The user interface (cards, panel, notifications) is in **French** only for now.
> This document quotes the French labels as they appear on screen, with an English gloss.
> Configuration values (`bloque`, `sur_demande`…) and action names (`devoirs_termines`…) are
> also French identifiers.

## Installation

Requirements: Home Assistant **2026.10** or later. To control AdGuard Home services, also
install [AdGuard Clients](https://github.com/cesbron-dev/ha-adguard-clients).

1. **Settings, Marketplace**, **Add from link** button in the top right corner, with the URL
   `https://github.com/cesbron-dev/ha-parental-control` (before Home Assistant 2026.11: HACS,
   top-right menu, **Custom repositories**, category **Integration**).
2. Install « Parental Control », then restart Home Assistant.
3. **Settings, Devices & services, Add integration, Contrôle parental** (the integration is
   listed under this name in Home Assistant, and as « Parental Control » in Marketplace).
4. Choose the **parent code**: 4 to 8 digits. It is stored hashed (PBKDF2), never in clear
   text. Only one instance of the integration is allowed. The code can be changed later in the
   integration options.

Once added, the integration has no configuration yet: build it in the
[Rules panel](#rules-panel) or load the JSON below.

## JSON configuration

### Annotated example

The JSON is a single document (remove the `//` comments below, JSON does not allow them).

```jsonc
{
  "version": 2,                       // always 2
  "services": [                       // your services (see "Configurable services"); display order
    {"id": "youtube", "name": "YouTube", "icon": "mdi:youtube", "adguard": ["youtube"]},
    {"id": "jeux_video", "name": "Jeux vidéo", "icon": "mdi:gamepad-variant",
     "adguard": ["roblox", "fortnite"],
     "labels": [{"label_id": "console", "on_means_allowed": false}]}
  ],
  "default_leisure": ["jeux_video"],  // ids of your services
  "default_on_demand": ["youtube"],
  "calendar_map": {                   // word (accent- and case-insensitive) -> day type
    "pédagogique": "conge_peda",
    "vacances": "vacances",
    "relâche": "vacances"
  },
  "notify": ["notify.mobile_app_iphone_de_marc"],   // parents' notify services
  "kids": [
    {
      "id": "hugo",                  // unique id, used by the actions
      "name": "Hugo",
      "emoji": "🎮",                  // optional (for the cards)
      "color": "#FF6B6B",             // optional (for the cards)
      "calendar": "calendar.ecole_primaire",   // optional: calendar giving the day type
      "leisure_add": [],              // leisure services added to default_leisure
      "leisure_remove": [],           // services removed from default_leisure
      "resource_modes": { "switch": "sur_demande" },   // optional, per resource
      "profiles": {
        "ecole": {                    // "ecole" and "fin_de_semaine" profiles are required
          "segments": [
            { "start": "00:00", "type": "bloque" },
            { "start": "15:25", "type": "libre" },
            { "start": "16:00", "type": "apres_devoirs" },
            { "start": "19:00", "type": "bloque" }
          ]
        },
        "fin_de_semaine": {
          "quota_minutes": 120,       // child's daily budget ("quota" segments)
          "segments": [
            { "start": "00:00", "type": "bloque" },
            { "start": "08:00", "type": "quota" },
            { "start": "20:00", "type": "bloque" }
          ]
        }
      }
    }
  ],
  "resources": [                      // logical devices
    {
      "id": "tv",
      "name": "Télé salon",
      "icon": "mdi:television",       // optional
      "owners": ["hugo"],
      "quota_minutes": { "fin_de_semaine": 180 },
      "devices": [                    // physical devices
        {
          "name": "Samsung",
          "integrations": [
            {
              "kind": "media_player",
              "entity_id": "media_player.tv_salon",
              "notify_service": null  // optional: "notify.xxx" to warn on the device
            },
            { "kind": "adguard_services", "device_id": "1ef9511faa6db9c5969524170a8fe8e3" }
          ]
        }
      ]
    },
    {
      "id": "iphone_hugo",
      "name": "iPhone Hugo",
      "owners": ["hugo"],
      "devices": [
        {
          "name": "iPhone Hugo",
          "integrations": [
            { "kind": "adguard_services", "device_id": "7c2a9e0b4d1f4e6a8b3c5d7e9f102132" }
          ]
        }
      ]
    },
    {
      "id": "switch",
      "name": "Switch",
      "owners": ["hugo"],
      "devices": [
        {
          "name": "Switch",
          "integrations": [
            {
              "kind": "nintendo",
              "device_id": "c52a9e7f10b84d3698e1f4a7d3b60c28",
              "limit_entity": "number.switch_papa_temps_d_ecran_max_aujourd_hui",
              "remaining_entity": "sensor.switch_papa_temps_d_ecran_restant",
              "used_entity": "sensor.switch_papa_temps_d_ecran_utilise"
            }
          ]
        }
      ]
    }
  ]
}
```

### Keys

**Root**

| Key | Purpose |
|---|---|
| `version` | Always `2`; any other value is rejected. |
| `services` | Your services (see [Configurable services](#configurable-services)): `id` (fixed, derived from the name), `name`, `icon` (optional), `adguard` (AdGuard Home service ids), `labels` (`label_id` and `on_means_allowed`). |
| `default_leisure` | Ids of your services treated as leisure (these are the ones the engine blocks and unblocks). Empty by default. An unknown id is dropped when the stored configuration is loaded; sent by the panel, it is rejected. |
| `default_on_demand` | Ids of your services that stay blocked even when the device is open: only an explicit permission opens them. |
| `calendar_map` | Maps a word searched in the title of the child's calendar "all-day" events to a day type. Accent- and case-insensitive substring match. |
| `notify` | Parents' `notify.*` services: warnings about the end of a child's time slot and about an AdGuard service opened by exception being blocked again. |
| `request_notify` | Parents' phones (`notify.mobile_app_…`) that receive and can answer the children's time requests. Distinct from `notify`. See [Time requests](#time-requests). |
| `kids` | List of children. |
| `resources` | List of controlled logical devices (see [Logical devices](#logical-devices)). |

**Child (`kids[]`)**

| Key | Purpose |
|---|---|
| `id`, `name` | Unique id and display name (required). |
| `emoji`, `color` | Decoration for the cards (optional). |
| `calendar` | `calendar.*` entity whose "all-day" events determine the day type. |
| `leisure_add`, `leisure_remove` | Adjust `default_leisure` for this child. |
| `on_demand_add`, `on_demand_remove` | Adjust `default_on_demand` for this child. |
| `target_label` | Optional HA label: switches carrying this label and a service label are controlled for this child (see [Configurable services](#configurable-services)). |
| `resource_modes` | Per resource `id`, overrides the timeline behaviour: `suit_frise` (follows the timeline, default), `sur_demande` (on demand), `bloque` (blocked) or `libre` (free). |
| `profiles` | One profile per day type: `ecole` (school), `fin_de_semaine` (weekend), `conge_peda` (in-service day), `vacances` (holidays). `ecole` and `fin_de_semaine` are required. |

**Profile**

| Key | Purpose |
|---|---|
| `segments` | The day's timeline (at least one segment). The first starts at `00:00`, `start` times (`HH:MM`) are strictly increasing; a segment lasts until the next one starts, or until midnight. |
| `quota_minutes` | The child's daily budget for `quota` segments measured by a timer (optional: without it, no limit). |
| `warn_minutes` (in a segment) | Notice before the end of the open slot, in minutes (default `5`). |

**Segment types**

| Type | Behaviour |
|---|---|
| `bloque` | Everything is blocked. |
| `libre` | Everything is allowed. |
| `apres_devoirs` | Allowed only after the day's `devoirs_termines` (homework done); otherwise the status is "waiting for homework". |
| `quota` | Allowed within the budget. For the child: a timer must be started (`demarrer_minuteur`), and the timer's duration is deducted from the profile's `quota_minutes`; AdGuard resources only open while that timer runs. Only a device with a media player (`media_player`) or a switch (`switch`) has its own budget, deducted from actual use: its `quota_minutes` for the day type, or failing that the most generous screen-time quota among the children concerned (see [Logical devices](#logical-devices)). Unlimited only if neither the device nor any of these children has a quota that day. The Switch has no quota on the engine side: grant it time with `ajouter_bonus` (`resource_id: switch`). |
| `sur_demande` | Blocked until a parent opens it (`exception` action with `open: true`); status "on demand". For the Switch, no exception: use `ajouter_bonus` with `resource_id: switch`. |

**Day type.** The child's calendar sets the type through `calendar_map`. Priority when events
overlap: `vacances`, then `conge_peda`, then `ecole` / `fin_de_semaine`. Without a recognised
event: `ecole` Monday to Friday, `fin_de_semaine` Saturday and Sunday. If the `conge_peda` or
`vacances` profile does not exist, the `fin_de_semaine` profile applies (and, for a resource,
its `fin_de_semaine` `quota_minutes`).

**Resource (`resources[]`, logical device)**

| Key | Purpose |
|---|---|
| `id`, `name` | Unique id and display name (required). |
| `icon` | `mdi:` icon (optional, otherwise inferred). |
| `owners` | List of child `id`s, which must exist. |
| `quota_minutes` | Optional object `{ "<day type>": minutes }`. |
| `target_label` | Optional HA label: switches carrying this label and a service label are controlled for this device (see [Configurable services](#configurable-services)). |
| `devices` | Physical devices: `{ "name": ..., "integrations": [...] }`. At least one integration in total. |

Each integration has a `kind`:

| `kind` | Own keys | Notes |
|---|---|---|
| `media_player` | `entity_id` (required), `notify_service` (optional) | Any media player, whatever the integration (Samsung/SmartThings, Android TV Remote, Google Cast…). Turned off when the rule is closed. Usage time is counted, `quota_minutes` applies. With Google Cast, turning off only stops casting: prefer the Android TV Remote entity of a Google TV. |
| `switch` | `entity_id` (required, `switch.*`), `turn_on_when_allowed` (optional, `false` by default) | Smart plug, PC screen… Turned off when the rule is closed (and again if turned back on). When on, it counts as in use: usage time is counted, `quota_minutes` applies. With `turn_on_when_allowed: true`, it is turned back on once when the device becomes "allowed" (end of a closed slot, end of the pause); never at HA startup, after saving the configuration, or by a service exception. Beware: cutting a PC's plug shuts it down abruptly, and a plug left on with nothing connected still consumes the quota. The panel offers neither the parental control's own switches nor configuration switches (AdGuard settings…). |
| `adguard_services` | `device_id` (required) | Device of a persistent client from the `adguard_clients` integration. The engine reads the `services` attribute of its "Services bloqués" (blocked services) sensor and writes through `adguard_clients.set_blocked_services` (one write per decision). Only the AdGuard services attached to your managed services are touched. |
| `nintendo` | `device_id`, `limit_entity`, `remaining_entity`, `used_entity` | All four are required; the three entities come from the Nintendo integration (today's limit as a `number`, remaining and used time as `sensor`s). Today's limit must stay at 0: time is granted through bonuses. |

## Logical devices

For the family, "the TV" is a single device, even if the engine has to control several pieces
of it. The configuration therefore has three levels:

1. the **logical device** (`resources[]`): the one used by the cards and the rules (children
   concerned, quota per day type, mode per child);
2. its **physical devices** (`devices`): simple labels for grouping, with no rule of their own;
3. their **integrations** (`integrations`): a `media_player`, a `switch`, an AdGuard client, a
   Nintendo console.

Example: the TV, with the Samsung (player and AdGuard client) and the Google TV (player and two
AdGuard clients, one local and one through the VPN).

```json
{
  "id": "tv",
  "name": "Télé",
  "icon": "mdi:television",
  "owners": ["hugo", "zoe"],
  "quota_minutes": { "fin_de_semaine": 90 },
  "devices": [
    {
      "name": "Samsung",
      "integrations": [
        { "kind": "media_player", "entity_id": "media_player.tv_salon" },
        { "kind": "adguard_services", "device_id": "1ef9511faa6db9c5969524170a8fe8e3" }
      ]
    },
    {
      "name": "Google TV",
      "integrations": [
        { "kind": "media_player", "entity_id": "media_player.google_tv" },
        { "kind": "adguard_services", "device_id": "5e3b8c1d9f7a4b2e6c0d8a1f3b5e7c92" },
        { "kind": "adguard_services", "device_id": "a4d8f6e2c0b14a39857e6d5c4b3a2918" }
      ]
    }
  ]
}
```

**Rules apply once, to the logical device.** When closed, the TV turns off all its players and
blocks the leisure services on every AdGuard client; « Autoriser » (Allow) opens everything,
« Arrêter » (Stop) closes everything. An exception on a service (YouTube) opens it on all the
device's AdGuard clients; if the device is closed, its players are not turned off (only that
service gets through); they are turned off again when the exception ends. The per-child mode
(`resource_modes`) is unique per logical device and applies to all its integrations.

**Quota.** For a device that contains a media player, time counts as soon as a player is on,
only once even if several run together: it is the device's shared counter. The budget is the
device's `quota_minutes` for the day type; failing that, the screen-time quota from the timeline
of each child concerned (with their bonuses), and since the device is shared, the most generous
of these quotas applies. No quota anywhere that day: no limit. This also applies to a single
TV. A device without a player (AdGuard only) opens during a child's timer and draws on their
budget.

**Nintendo.** A console must be alone in its logical device: a single `nintendo` integration,
nothing else. Otherwise the engine rejects the configuration (« une console Nintendo ne se
regroupe pas », a Nintendo console cannot be grouped). Its behaviour is unchanged (bonuses, no
exceptions).

**Missing integration.** A player, AdGuard client or console that cannot be found in Home
Assistant (an unplugged Chromecast, for example) is reported once in the logs and ignored: the
device's other integrations keep being controlled.

### Loading the configuration

- Action **`parental_control.importer_configuration`** (parents only: rejected for other
  accounts; a call without a user, from an automation or a script, is also accepted) with the
  `config` field holding the JSON object. Like saving from the panel, it determines the owner of
  each phone in `request_notify` (the file's `request_notify_owners` key is ignored): an import
  that adds a phone without a unique `mobile_app` device fails. Developer tools, Actions, YAML
  mode:

  ```yaml
  action: parental_control.importer_configuration
  data:
    config:
      version: 2
      kids: []
      resources: []
  ```

- Or the WebSocket command **`parental_control/config/set`**
  (`{"type": "parental_control/config/set", "config": {...}}`, parents only).
  `parental_control/config/get` returns the current configuration (parents only too: it contains
  device ids and notification targets), `parental_control/state` the current state, and
  `parental_control/state/subscribe` subscribes to changes (for the cards).

An invalid configuration is rejected with the faulty path (for example
`kids[0].profiles.ecole.segments[2].start : heure invalide`, invalid time). If the stored
configuration is invalid at startup, the engine stays inactive: the error is logged and a
persistent notification « Contrôle parental : configuration invalide, moteur inactif » (invalid
configuration, engine inactive) is shown (it disappears once a valid configuration is loaded).

When a configuration removes a child or a resource, the decisions that targeted them
(exceptions, timers, bonuses, homework) are deleted.

## Actions

The "code" is the parent code. A **parent** (see [Who is a parent](#who-is-a-parent)), or a call
**without a user** (automation, script), does not need to provide it. Any other user must pass
it in the `code` field for actions that unblock something.

| Action | Fields | Code required (non-parent) |
|---|---|---|
| `parental_control.devoirs_termines` (homework done) | `kid_id` | yes |
| `parental_control.ajouter_bonus` (add bonus) | `minutes` (1 to 240) and exactly one of `kid_id` or `resource_id` | yes |
| `parental_control.exception` | `open` (required), `resource_id`, `kid_id`, `service`, `minutes` (1 to 240) | yes if `open: true`, no for a closure |
| `parental_control.annuler_exception` (cancel exception) | `exception_id` | yes if the cancelled exception is a closure (cancelling reopens) |
| `parental_control.demarrer_minuteur` (start timer) | `kid_id`, `minutes` (1 to 240) | yes |
| `parental_control.arreter_minuteur` (stop timer) | `kid_id` | no |
| `parental_control.pause` | `active` | yes to lift the pause (`active: false`), no to set it |
| `parental_control.importer_configuration` (import configuration) | `config` | parents only (rejected for others, with or without code) |
| `parental_control.demander` (request) | `kind`, `kid_id`, `resource_id`, `service`, `minutes`, `options`, `replace` | no (see [Time requests](#time-requests)) |

Details:

- `ajouter_bonus` on a `kid_id` adds minutes to the child's quota for the day; on a
  `resource_id` with a player or a switch, to the resource's quota; on a `nintendo` resource,
  grants play time to the console. No bonus for AdGuard.
- `exception` without `service` requires a `resource_id` (a precise target). With `service`, the
  target is one of your services (its id), for one resource, for all of a child's resources, or
  for all resources. An exception on the Switch is rejected (« Pour la Switch, utilisez
  ajouter_bonus », use ajouter_bonus for the Switch). Without `minutes`, the exception lasts
  until the next rule change; with `minutes`, for that duration. The action returns
  `{"id": "..."}` when a response is requested (`response_variable`): it is the `exception_id`
  to pass to `annuler_exception`.
- Ongoing exceptions are listed in the status sensor's attributes.

## Entities

Each child, each resource and the global pause are devices (of type "service").

| Entity | Details |
|---|---|
| `sensor` Status, per child | States: `autorise` (allowed), `bloque` (blocked), `attente_devoirs` (waiting for homework), `attente_minuteur` (waiting for a timer), `quota_epuise` (quota used up), `sur_demande` (on demand), `pause`. Snapshot details (day type, segment, slot end, remaining time, exceptions) are attributes. |
| `button` Homework done, per child | Same as the `devoirs_termines` action, without code for a parent; a button cannot carry a code, so it is rejected for other users (use the action with `code`). |
| `binary_sensor` Allowed, per resource | Open according to the rule. For AdGuard, the blocked services are an attribute. |
| `sensor` Time used / Time remaining, per resource | Minutes, only for devices with a player, a switch or a Nintendo console. |
| `switch` Global pause | Closes all resources (on AdGuard, the leisure services) and resets the Nintendo daily limit to 0. Anyone can set it; turning it off is rejected for a non-parent (a switch cannot carry a code: use the `pause` action with `code`). A parent turns it off without code. |
| `switch` Simulation | See [Simulation mode](#simulation-mode). |

Entity ids are the ones Home Assistant generates from the names (for example
`sensor.hugo_statut` if the device is called "Hugo").

### `parental_control_warning` event

Fired before a scheduled closure, at the segment's notice (`warn_minutes`, 5 min by default, the
smallest among the owners for a resource):

```yaml
event_type: parental_control_warning
data:
  target: "kid:hugo"        # or "resource:tv", or "service:iphone_hugo:youtube"
  closes_at: "2026-10-29T19:00:00-04:00"
  message: "Hugo : fin des écrans dans 5 min"
```

A `service:<resource>:<service>` target reports an unblocked AdGuard service (for example opened
by exception) that is about to be blocked again while the resource stays closed; message:
« YouTube sur iPhone Hugo : coupure dans 5 min » (cut in 5 min).

For a child or a service, the message is also sent to the `notify` services; messages for the
same closing time are grouped into a single notification. For a resource, it is sent through
its `notify_service` if set.

## Cards

The integration loads its cards into the dashboard by itself (no resource to add); they appear
in the card picker under « Contrôle parental ». They read the engine's state live and only call
the `parental_control.*` actions. `resource` is the `id` of a resource from the configuration.
Each card has a visual editor (the card's "Edit" button): the device and children are picked
from lists drawn from the rules, and options (name, icon, title, bonus minutes) are filled in
without YAML; "Show code editor" remains available. After an update, restart Home Assistant:
the cards' address changes with their content, which keeps a browser from holding on to an old
version.

| Card | Purpose | Minimal configuration |
|---|---|---|
| `parental-resource-card` | A device: state, ongoing permissions (✕ to cancel), « Autoriser… » (Allow…) and « Arrêter » (Stop). For a Switch: bonus pills instead. AdGuard device or device targeted by a labelled switch: its on-demand services as toggles (green unblocked, grey blocked). | `resource: tv` |
| `parental-timeline-card` | Each child's timeline for the day. | `type: custom:parental-timeline-card`; `kids: [hugo]` restricts to the listed children |
| `parental-kid-card` | A child: status, today's timeline, « Devoirs terminés » (homework done, during an after-homework slot), timer (quota slot), remaining screen time, on-demand services as toggles (AdGuard devices and switches targeting the child), ongoing permissions (✕) and bonuses. | `kid: alice`; `show_timeline`, `show_services`, `show_bonus` (false to hide), `services`, `bonus_minutes` |
| `parental-switch-card` | A Nintendo console: remaining-time gauge, time used, rule state and bonuses. Complements the official Nintendo integration. | `resource: switch` |

```yaml
type: custom:parental-resource-card
resource: tv
services: [youtube]           # optional: on-demand services shown (all by default)
show_services: false          # optional: hides the service toggles
```

**Service toggles.** The card shows the device's on-demand services. Tapping a blocked service
opens a dialog to choose the duration (15 min to 2 h) or "until the next slot change", with the
code for a non-parent account; tapping an unblocked service blocks it, without code. The cards
follow Home Assistant's light or dark theme.

```yaml
type: custom:parental-switch-card
resource: switch
title: Nintendo Switch        # optional
bonus_minutes: [15, 30, 60]   # optional
```

**The parent code.** A non-parent account must enter the code (small padlock on the pill) to
**allow**, grant **bonuses**, confirm **homework** and start a **timer**. It is typed on an
on-screen keypad (no native keyboard covering the screen; a physical keyboard also works), sent
with the call and forgotten; it is never stored in a card or in the dashboard configuration.
« Arrêter » (Stop) and ✕ go through without code, after a two-tap confirmation.

## Rules panel

The integration adds a **Règles** (Rules) panel to the sidebar to edit the configuration
without writing JSON: children and timelines per day type (segments, quotas, warnings), leisure
services, mode per device, logical devices as a tree (physical devices, then integrations:
player, switch, AdGuard clients, Nintendo console, with a badge telling whether the entity or
device exists in Home Assistant) and their quotas, your services, default leisure services,
school-calendar words and notifications. Changes stay as a draft until « Enregistrer » (Save);
the engine validates them and, on error, points to the faulty field. A JSON tab keeps access to
the raw configuration.

### Who is a parent

The following can open and edit the panel (JSON tab and parents' phone list included), without
code and without « Demander » (Request):

- Home Assistant **administrators**;
- non-administrator users who **own a phone** listed under « Demandes de temps (parents) »
  (parents' time requests, see [Time requests](#time-requests)).

The « Règles » entry is visible in every account's sidebar, but a non-parent account only reads
« Réservé aux parents. » (parents only): the server also refuses `config/get`, `config/set` and
`services/catalog` to non-parents (`unauthorized`). A disabled administrator account no longer
skips the code.

## Configurable services

A **service** is defined by the parent in the « Règles » panel, « Général » (General) tab,
« Services » card: a name, an icon, and what actually blocks it:

- one or more **AdGuard Home services**, picked by name from the AdGuard catalog;
- and/or one or more **HA labels** set on `switch` entities (a UniFi firewall rule, etc.).

Example: « Jeux vidéo » (video games) = Roblox and Fortnite (AdGuard) + the « Console » label,
set on a UniFi rule "Cut console internet". Blocking « Jeux vidéo » blocks all of it at once; an
exception or an accepted request opens it the same way.

Only these services appear elsewhere: leisure and on-demand lists (default and per child),
access requests, exceptions, notifications, cards. The AdGuard catalog is only used to choose
what to attach.

- **AdGuard.** An AdGuard client blocks the union of the AdGuard services of the blocked
  services. The same AdGuard service can belong to several services: it is blocked as soon as
  one managed service containing it is blocked. AdGuard services that you have not attached to
  any managed service are never touched. Removing an AdGuard service from a service (or deleting
  a service) while it is blocked leaves it blocked on the client: unblock it in AdGuard if
  needed.
- **Switches.** A `switch` that carries a label attached to a service and the **target label**
  of a child or a logical device (the « Label de cible » field of the child or device) is
  controlled for that target. By default, **on = blocked**, like an active firewall rule; the
  « Allumé = autorisé » (on = allowed) option is set **per label**.
- **Child or device target.** With a child as target, the switch follows the child's state (and
  the exceptions targeting the child or one of their devices); with a device, it follows the
  service's state for that device, even without an AdGuard client. Several targets: blocked as
  soon as one requires it.
- **A label** is attached to a single service, and is never both attached and a target label:
  the panel refuses the combination.
- **Exceptions.** A permission on a service that only has labels opens only its switches: it
  does not keep a closed device's players or plug on. Closing warnings only concern the AdGuard
  part of services.
- **Pause.** The global pause also blocks these services (if they are managed).
- **Ignored cases.** A switch is left as is:
  - without a target, or if its label was deleted: warning in the log and in the « Interrupteurs
    pilotés » (controlled switches) summary of the Services card (in red);
  - if its service is neither leisure nor on demand for any target: "not managed" state;
  - if it is unavailable: warning in the log; it is controlled again as soon as it comes back.

## Time requests

A child who is not a parent can **request** time instead of unlocking it: the cards' dialogs
(permission, bonus, homework, timer) have a « Demander » (Request) button, without code. Parents
get an actionable notification in the Home Assistant app (« Hugo demande 30 min de YouTube sur
iPhone Hugo », Hugo asks for 30 min of YouTube on Hugo's iPhone) with one button per offered
duration and « Refuser » (Decline). The first valid answer applies the action (exception, bonus,
timer or homework done); the notification disappears for all parents. The child's card shows
« Demande envoyée · en attente » (request sent, pending), then the outcome (accepted, declined,
no answer) for 5 minutes.

**Enabling.** In the « Règles » panel, « Demandes de temps (parents) » card, add the parents'
phones (`request_notify` key, for example `notify.mobile_app_iphone_de_marc`). Without this
list, requests are disabled. This list is distinct from `notify`, which is used for closing
warnings aimed at the children.

**Phone owner.** On save (or import), the server looks for the `mobile_app` device with the same
name as each phone and remembers the user it belongs to (`request_notify_owners` key, written by
the server: a value sent by the client, panel or import, is ignored). That owner is a parent as
long as the device still belongs to them, unambiguously. Each saved phone shows a status and the
remembered owner's name in the panel; a phone that was just added only gets a status after
saving:

| Status | Meaning |
|---|---|
| Associé (linked) | Owner remembered, device still theirs. |
| À associer (to link) | No remembered owner: « Réassocier à <name> » (relink to <name>). |
| Appareil introuvable (device not found) | No `mobile_app` device with this name. |
| Changé de compte (account changed) | The device now belongs to another user: « Réassocier à <name> ». |
| Nom en double (duplicate name) | Several devices have this name: rename them. |

The « Réassocier à <name> » button only exists for « À associer » and « Changé de compte »; it
names the device's current account, which becomes a parent on save. Removing your own last
phone asks for confirmation (« Vous ne serez plus parent après l'enregistrement. Continuer ? »,
you will no longer be a parent after saving).

**Reinstalling the Home Assistant app** on a phone (the `mobile_app` device is recreated):

- same account, old device deleted from Home Assistant: the phone stays « Associé », nothing to
  do;
- old device kept: « Nom en double »; delete (or rename) the old device in Settings → Devices &
  services → Mobile App;
- new device named with a suffix (`iPhone de Julie 2`, for example): the old phone becomes
  « Appareil introuvable »; remove that target and add the new one;
- another account on the same device name: « Changé de compte », then « Réassocier à <name> » if
  that account should be a parent.

**« Demandes » (Requests) screen.** The integration creates the `/parental-control-requests`
screen: no dashboard to set up. It lists pending requests with their remaining time and the same
buttons as the notification, then the answers from the last 5 minutes (who answered, what was
granted). It updates live. Any user can open it, but only parents (as defined below) see the
buttons, and the engine re-checks each answer. On iPhone, a long press on the notification also
lets you answer without opening the app.

The screen has no sidebar entry, so that children do not see it. You get there:

- by tapping a request notification;
- **parents** (administrators or not): through the « Demandes » button of the « Règles » panel,
  which shows the number of pending requests;
- **without the panel** (if you prefer not to use it): the notification is no longer enough
  once it has been dismissed or cleared. To get back to the screen:
  - in a browser, open `https://<your-instance>/parental-control-requests` and bookmark it;
  - or add a button to a dashboard this parent uses. The `user` visibility condition hides it
    from other accounts, including the children's tablet (the id is under Settings → People →
    Users):

    ```yaml
    type: button
    name: Demandes
    icon: mdi:hand-back-right
    tap_action:
      action: navigate
      navigation_path: /parental-control-requests
    visibility:
      - condition: user
        users:
          - <id of the parent's user>
    ```

**Who can answer.** An answer is only accepted if it comes from the **user who owns a listed
phone** (remembered owner, see above), from the notification (which also carries the request's
own **secret token**) or from the « Demandes » screen: being an administrator is not enough, and
a parent without a listed phone cannot answer. If two `mobile_app` devices have the same name,
neither can answer (a warning is logged): give them distinct names.

**Rules.**

- An impossible request (unknown target, resource that does not belong to the child, bonus not
  applicable to the resource…) is rejected when sent, not when the parent answers.
- Only one pending request per child and per action.
- Without an answer after **15 minutes**, the request expires.
- Requests are kept **in memory**: they are lost when Home Assistant restarts (the notification
  then stays on the phone, but its answer is ignored).
- Each outcome (accepted, declined, impossible, no answer) leaves a line in the logbook
  (« Contrôle parental »).
- An **iPhone** is recommended: Android shows at most 3 buttons per notification, which cuts the
  offered durations.

**`parental_control.demander` action.** Used by the cards; can also be called from a script or
an automation. It asks for no code and grants nothing until a parent has answered. With
`response_variable`, it returns `{"id": "..."}`.

| Field | Details |
|---|---|
| `kind` | `open` (allow), `bonus`, `homework` (homework done) or `timer`. Required. |
| `kid_id` | The requesting child. Required. |
| `resource_id` | The targeted resource (`open` and `bonus` only); it must belong to the child. |
| `service` | Id of one of your services to unblock (`open`). |
| `minutes` | Offered duration (1 to 240), required for `bonus` and `timer`, forbidden for `homework`. Shown first among the buttons. |
| `options` | Other offered durations, in minutes; `null` for `open` = "until the next change". At most six duration buttons. |
| `replace` | Ids of exceptions to cancel when the parent accepts (`open`). |

## Simulation mode

Simulation mode runs the whole engine (states, timelines, exceptions, warnings) without
controlling any device: nothing is blocked, turned off or limited. It is used to check the rules
before letting them act.

- **Switch**: a « Simulation » `switch`, next to « Pause ». The cards show a « SIMULATION » badge
  in their header and the « Règles » panel a banner at the top.
- **Logbook.** Every action the engine would have taken (closing a resource, blocking a service
  again, resetting the Nintendo limit to 0…) is recorded there instead of the real call.
- **Installation.** A new installation starts in simulation: turn it off once the rules are
  checked.
- **Parent code.** **Turning on** simulation releases every device: a non-parent account must
  therefore provide the parent code. A switch cannot carry a code: it is rejected for a
  non-parent, as for lifting the pause. A parent turns it on without code. Turning it off needs
  none.
- **Notifications.** Notifications to parents are still sent, prefixed with « [Simulation] ».
- **Leaving simulation.** When it is turned off, the engine immediately reapplies the intended
  state to every device.

## Wall tablet

1. Create a **dedicated, non-administrator Home Assistant user** for the tablet.
2. Show the dashboard there. The [cards](#cards) ask for the code to unlock; the « Devoirs
   terminés » (homework done) button and lifting the pause remain refused on the tablet: parents
   use them from their phone (administrator, or parent declared in « Demandes de temps »).
3. Actions that unlock something require the **parent code** in the `code` field of an action
   call. **Never write the code** in a dashboard `perform-action`, nor in an automation or a
   script that a non-parent can trigger.
4. **Hide the raw AdGuard** (`adguard_clients` devices), **Nintendo and TV entities** from the
   tablet user: they could manipulate them directly. The engine corrects a drift (AdGuard
   service unblocked during a closure, TV turned back on, Nintendo limit raised), but not before
   it has happened.
5. **Lockout**: after 5 consecutive wrong codes, attempts are refused for 60 s; each further
   failure doubles the duration, up to 15 minutes. A correct code resets the counter. The counter
   is per user and **in memory**: a Home Assistant restart resets it.

## Known limitations

- **Calls without a user.** An automation or a script calls actions without a user: the code is
  then not required. Do not create an automation or a script that unblocks something and that a
  non-parent user can trigger (`automation.trigger`, `script.turn_on`, etc.): that would bypass
  the code.
- **AdGuard.** The device comes from the configuration (`device_id`); its "Services bloqués"
  sensor is looked up when the engine starts. A missing or unavailable sensor is reported in the
  logs and ignored: **services are then not blocked on that device**. A client set to "Use
  global blocked services" does not apply its own list: the engine writes it anyway and warns in
  the logs; turn that setting off on the children's devices. A device created after the engine
  started requires reloading the integration.
- **Removing a leisure service.** Removing a service from `default_leisure` (or through
  `leisure_remove`) while it is blocked leaves it blocked: the engine no longer manages it.
- **Nintendo.** The engine never cuts a game in progress: it only grants bonus time (30-minute
  chunks per call, 5 s apart) and keeps the daily limit at 0. A raised limit (for example from
  the tablet) is reset to 0. The global pause also resets the limit to 0; it has **not been
  checked on a real console** whether this cuts a bonus already granted. The
  `nintendo_parental_controls.add_bonus_time` action called directly cannot be controlled by the
  engine (it does not take back a bonus): hide it and do not let the tablet user call it.
- **Child status.** The status sensor follows the timeline: it does not reflect manual
  exceptions (a resource opened by exception changes nothing there).
- **Timer past midnight.** A timer that crosses midnight is counted entirely on the day it
  started.
- **Pause and exceptions.** During the pause, "until the next rule change" exceptions do not
  expire.
- **Restart and exceptions.** A non-leisure service blocked by an exception stays blocked after
  a Home Assistant restart (fail closed), until a parent unblocks it.
- **TV accuracy.** Usage is counted once per minute (± 1 minute accuracy).
- **The code is a string.** Send it in quotes: in YAML, `code: 0123` becomes the integer `123`.

## Development

```bash
uv venv --python 3.14 .venv
uv pip install --python .venv/bin/python -r requirements_test.txt
.venv/bin/pytest
node --test tests/js/*.test.mjs
```
