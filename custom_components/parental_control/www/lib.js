// Bibliothèque partagée des cartes Contrôle parental : fonctions pures, sans DOM.
// Les fonctions qui produisent du texte prennent `hass` en dernier paramètre (langue de
// l'utilisateur, anglais sans `hass`).
import { t, hasKey, formatTime, formatClock, formatDuration, durationText } from "./i18n.js";

// Échappe un texte venant du moteur avant de l'insérer dans du HTML.
export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);
}

// Durée en minutes des jauges : « 1h 05m » en français, « 1 h 5 min » en anglais (négatif ou
// invalide -> zéro).
export function fmtDuration(minutes, hass) {
  const total = Math.max(0, Math.round(Number(minutes) || 0));
  return durationText(hass, "duration.compact", total);
}

// Raison du moteur d'un enfant ou d'une ressource dans la langue de l'utilisateur
// (`reason_code` et `reason_params`) ; code inconnu : texte du serveur (`reason`), sinon le code.
// L'heure de `allowed_until` suit le format de l'utilisateur : celle de `until` (ISO, fuseau du
// navigateur comme les autres heures des cartes), à défaut le paramètre « HH:MM » du moteur.
export function reasonText(item, hass) {
  const code = item?.reason_code;
  if (code && hasKey(`reason.${code}`)) {
    const params = { ...(item.reason_params ?? {}) };
    if (code === "allowed_until") params.until = item.until ? formatTime(hass, item.until) : formatClock(hass, params.until);
    return t(hass, `reason.${code}`, params);
  }
  return item?.reason || code || "";
}

// Raison de l'échec d'une demande : `request.reason.<code>`, puis `error.<code>` (erreur d'une
// action du parent), sinon le texte du serveur.
function requestReason(req, hass) {
  const code = req?.reason_code;
  const params = req?.reason_params ?? {};
  if (code && hasKey(`request.reason.${code}`)) return t(hass, `request.reason.${code}`, params);
  if (code && hasKey(`error.${code}`)) return t(hass, `error.${code}`, params);
  return req?.reason || code || "";
}

// `services` : services du parent (`state.services`, `{id: {name, icon, adguard, labels}}`).
// Id inconnu : l'identifiant capitalisé.
export function serviceLabel(id, services = null) {
  const name = services?.[id]?.name;
  if (name) return name;
  const s = String(id ?? "");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

// Icône MDI d'un service du parent, ou null.
export function serviceIcon(id, services = null) {
  return services?.[id]?.icon ?? null;
}

// Un service est-il montré sur un appareil ? Oui s'il concerne AdGuard et que l'appareil est un
// appareil AdGuard, ou si l'appareil est la cible d'un interrupteur de ses labels (`label_services`).
export function serviceShownOnResource(state, resource, service) {
  const adguard = (resource?.kinds ?? [resource?.kind]).includes("adguard_services");
  return (adguard && !!state?.services?.[service]?.adguard)
    || (resource?.label_services ?? []).includes(service);
}

// Le compte non admin doit saisir le code parent pour ouvrir (open, bonus, devoirs, minuteur),
// pas pour fermer. Un parent non admin (`parent`) n'en a pas besoin non plus.
export function needsCode(hass, action, parent = false) {
  if (hass?.user?.is_admin || parent) return false;
  return ["open", "bonus", "homework", "timer"].includes(action);
}

// Un compte non admin peut envoyer une demande de temps quand le moteur l'a activée.
export function canRequest(hass, state, parent = false) {
  return !hass?.user?.is_admin && !parent && !!state?.requests_enabled;
}

// Demande qui correspond à la cible, la plus récente (même délai pour toutes : `expires` le plus loin).
export function findRequest(state, { kind, kid_id, resource_id = null, service = null }) {
  let best = null;
  for (const r of state?.requests ?? []) {
    if (r.kind !== kind || r.kid_id !== kid_id) continue;
    if ((r.resource_id ?? null) !== resource_id || (r.service ?? null) !== service) continue;
    if (!best || new Date(r.expires) > new Date(best.expires)) best = r;
  }
  return best;
}

// Demandes d'un enfant (`{kid_id}`) ou d'une ressource (`{resource_id}`).
export function requestsFor(state, { kid_id, resource_id }) {
  return (state?.requests ?? []).filter((r) => (resource_id ? r.resource_id === resource_id : r.kid_id === kid_id));
}

// Enfants propriétaires d'une ressource, en choix `{value, label}` pour « Qui demande ? ».
export function ownerChoices(state, owners) {
  return (owners ?? []).map((id) => ({ value: id, label: state?.kids?.[id]?.name ?? id }));
}

// Durée d'une demande, comme `duration_label` du moteur : « 15 min », « 1 h », « 1 h 30 ».
function requestDuration(minutes, hass) {
  if (minutes == null) return t(hass, "request.until_next_change");
  return formatDuration(hass, minutes);
}

// Ligne d'état d'une demande, affichée sous les pastilles de la carte.
export function requestLine(req, hass) {
  switch (req.status) {
    case "pending": return t(hass, "request.line.pending");
    case "accepted": return req.kind === "homework" ? t(hass, "request.line.accepted")
      : t(hass, "request.line.accepted_duration", { duration: requestDuration(req.granted, hass) });
    case "refused": return t(hass, "request.line.refused");
    case "expired": return t(hass, "request.line.expired");
    default: return t(hass, "request.line.failed", { reason: requestReason(req, hass) });
  }
}

// Texte d'une demande pour l'écran « Demandes », dans la langue de l'utilisateur, d'après les
// champs sans langue du serveur (noms, `proposed`) ; même choix de gabarit que
// `ParentalEngine.request_message` (notification, langue système). Sans ces champs : `message`.
export function requestMessage(req, hass) {
  if (!req?.kid_name) return req?.message ?? "";
  const params = { kid: req.kid_name };
  if (req.resource_name) params.resource = req.resource_name;
  if (req.proposed != null) params.duration = formatDuration(hass, req.proposed);
  switch (req.kind) {
    case "homework": return t(hass, "request.homework", params);
    case "bonus": return t(hass, params.resource ? "request.bonus_on" : "request.bonus", params);
    case "timer": return t(hass, "request.timer", params);
    case "open": {
      if (req.service_name) params.service = req.service_name;
      const parts = ["duration", "service", "resource"].filter((p) => p in params);
      if (req.proposed == null) parts.push("until");
      return t(hass, `request.open.${parts.join("_")}`, params);
    }
    default: return req.message ?? "";
  }
}

// Titre d'un bouton de réponse ({choice, label, minutes}) dans la langue de l'utilisateur :
// `duration` -> la durée seule (null : « Jusqu'au prochain changement ») ; sinon `request.<label>`.
export function choiceTitle(choice, hass) {
  const duration = formatDuration(hass, choice.minutes);
  if (choice.label === "duration") return duration;
  return t(hass, `request.${choice.label}`, { duration });
}

// Temps restant avant l'expiration d'une demande en attente, pour l'écran « Demandes ».
export function requestRemaining(expires, now, hass) {
  const minutes = Math.ceil((new Date(expires) - now) / 60000);
  if (!(minutes > 0)) return t(hass, "request.expires_now");
  return minutes === 1 ? t(hass, "request.expires_in_one") : t(hass, "request.expires_in", { minutes });
}

// Issue d'une demande traitée, pour l'écran « Demandes » : qui a répondu et ce qui a été accordé.
export function requestOutcome(req, hass) {
  const parent = req.answered_by || null;
  const by = parent ? "_by" : "";
  const key = (name) => `request.outcome.${name}`;
  switch (req.status) {
    case "accepted":
      return req.kind === "homework" ? t(hass, key(`accepted${by}`), { parent })
        : t(hass, key(parent ? "accepted_by_duration" : "accepted_duration"),
          { parent, duration: requestDuration(req.granted, hass) });
    case "refused": return t(hass, key(`refused${by}`), { parent });
    case "expired": return t(hass, key("expired"));
    default: return t(hass, key(`failed${by}`), { parent, reason: requestReason(req, hass) });
  }
}

// Nombre de demandes en attente (pastille du bouton « Demandes » du panneau « Règles »).
export function pendingCount(state) {
  return (state?.requests ?? []).filter((r) => r.status === "pending").length;
}

// Demandes de l'écran : en attente (la plus ancienne d'abord) puis récentes (la plus récente d'abord).
export function requestsScreen(requests) {
  const list = requests ?? [];
  const byCreated = (a, b) => new Date(a.created) - new Date(b.created);
  return {
    pending: list.filter((r) => r.status === "pending").sort(byCreated),
    recent: list.filter((r) => r.status !== "pending").sort((a, b) => byCreated(b, a)),
  };
}

function scopeOf(target) {
  if (target.resource_id) return "resource";
  if (target.kid_id) return "kid";
  return "all";
}

// Exceptions ouvertes qui touchent une ressource (cible ressource, enfant propriétaire ou globale).
export function exceptionsForResource(state, resourceId, hass) {
  const resource = state?.resources?.[resourceId];
  if (!resource) return [];
  const out = [];
  for (const e of state.exceptions ?? []) {
    if (!e.open) continue;
    const tg = e.target ?? {};
    const touches = tg.resource_id
      ? tg.resource_id === resourceId
      : tg.kid_id
        ? (resource.owners ?? []).includes(tg.kid_id)
        : true;
    if (!touches) continue;
    // Une exception de service ne concerne que les appareils AdGuard ou ceux d'un interrupteur par label.
    if (tg.service && !(resource.kinds ?? [resource.kind]).includes("adguard_services")
      && !(resource.label_services ?? []).includes(tg.service)) continue;
    const scope = scopeOf(tg);
    out.push({
      id: e.id,
      label: tg.service ? serviceLabel(tg.service, state.services) : t(hass, "exception.whole_device"),
      service: tg.service ?? null,
      scope,
      kid: scope === "kid" ? (state.kids?.[tg.kid_id]?.name ?? tg.kid_id) : null,
      until: e.until ?? null,
      endsAt: e.ends_at ?? null,
    });
  }
  return out;
}

// Exceptions ouvertes qui touchent un enfant (lui, une de ses ressources, ou globale).
export function exceptionsForKid(state, kidId) {
  const out = [];
  for (const e of state?.exceptions ?? []) {
    if (!e.open) continue;
    const tg = e.target ?? {};
    const touches = tg.resource_id
      ? (state.resources?.[tg.resource_id]?.owners ?? []).includes(kidId)
      : tg.kid_id
        ? tg.kid_id === kidId
        : true;
    if (touches) out.push({ id: e.id, endsAt: e.ends_at ?? null, scope: scopeOf(tg) });
  }
  return out;
}

export function formatPill(exc, now, hass) {
  let when;
  if (exc.until) {
    // durée restante en minutes arrondies au-dessus : « 42 min », « 1 h 15 »
    when = formatDuration(hass, Math.max(0, Math.ceil((new Date(exc.until) - now) / 60000)));
  } else if (exc.endsAt) {
    when = t(hass, "time.until", { time: formatTime(hass, exc.endsAt) });
  } else {
    when = t(hass, "time.until_further_notice");
  }
  let text = `${exc.label} · ${when}`;
  if (exc.scope === "kid") text += ` · ${t(hass, "exception.kid_all_devices", { kid: exc.kid })}`;
  else if (exc.scope === "all") text += ` · ${t(hass, "exception.everyone")}`;
  return text;
}

// Vue d'une ressource pour l'affichage ; `status` distingue moteur sans snapshot et ressource inconnue.
export function resourceView(state, resourceId) {
  const resources = state?.resources ?? {};
  const base = {
    status: "ok", name: null, kind: null, kinds: [], icon: null, owners: [], open: false,
    reason: "", reason_code: null, reason_params: {}, until: null,
    used: null, remaining: null, leisure: [], onDemand: [], nintendo: null, paused: !!state?.paused, resumesAt: null,
  };
  if (Object.keys(resources).length === 0) return { ...base, status: "unavailable" };
  const r = resources[resourceId];
  if (!r) return { ...base, status: "unknown" };
  return {
    ...base,
    name: r.name,
    kind: r.kind,
    kinds: r.kinds ?? [r.kind],
    icon: r.icon ?? null,
    owners: r.owners ?? [],
    open: !!r.open,
    reason: r.reason ?? "",
    reason_code: r.reason_code ?? null,
    reason_params: r.reason_params ?? {},
    until: r.until ?? null,
    used: r.used_minutes ?? null,
    remaining: r.remaining_minutes ?? null,
    leisure: r.leisure ?? [],
    onDemand: r.on_demand ?? [],
    nintendo: r.kind === "nintendo"
      ? { used_entity: r.used_entity, remaining_entity: r.remaining_entity }
      : null,
    resumesAt: r.kind === "nintendo" ? null : blockedSegmentEnd(state.kids, r.owners),
  };
}

// Services sur demande affichés sur la carte d'un appareil, avec leur état actuel (débloqué ou
// non, d'après `blocked_services` du moteur) ; un service n'est montré que s'il concerne AdGuard
// (appareil AdGuard) ou vise l'appareil par ses labels (`label_services`). `only` (liste
// d'ids, config de la carte) restreint et ordonne l'affichage. `exceptions` : ids des exceptions
// de ce service posées sur cet appareil (à remplacer lors d'une bascule, pour ne pas les empiler).
export function serviceToggles(state, resourceId, only = null) {
  const r = state?.resources?.[resourceId];
  if (!r) return [];
  const onDemand = (r.on_demand ?? []).filter((s) => serviceShownOnResource(state, r, s));
  if (!onDemand.length) return [];
  const ids = Array.isArray(only) && only.length ? only.filter((s) => onDemand.includes(s)) : onDemand;
  const blocked = new Set(r.blocked_services ?? []);
  return ids.map((service) => ({
    service,
    label: serviceLabel(service, state.services),
    icon: serviceIcon(service, state.services),
    open: !blocked.has(service),
    exceptions: (state.exceptions ?? [])
      .filter((e) => e.target?.resource_id === resourceId && e.target?.service === service)
      .map((e) => e.id),
    // Ouvert par une exception d'enfant ou globale : le bloquer demande une fermeture, pas
    // seulement d'annuler les exceptions de cet appareil.
    openedElsewhere: exceptionsForResource(state, resourceId).some((e) => e.service === service && e.scope !== "resource"),
  }));
}

// Choix du dialogue « Autoriser… » d'un appareil : l'appareil entier, puis ses services (sur
// demande d'abord : ils ne s'ouvrent que par une autorisation, puis loisirs). Même filtre que
// `serviceToggles` : un service concernant AdGuard est proposé sur un appareil AdGuard, un service
// à labels seulement si l'appareil est la cible d'un de ses interrupteurs (`label_services`).
export function allowChoices(state, resourceId, hass) {
  const choices = [{ value: null, label: t(hass, "exception.whole_device") }];
  const r = state?.resources?.[resourceId];
  if (!r) return choices;
  const shown = (s) => serviceShownOnResource(state, r, s);
  const onDemand = (r.on_demand ?? []).filter(shown);
  for (const s of onDemand) choices.push({ value: s, label: t(hass, "exception.on_demand", { service: serviceLabel(s, state.services) }) });
  for (const s of (r.leisure ?? []).filter(shown)) {
    if (!onDemand.includes(s)) choices.push({ value: s, label: serviceLabel(s, state.services) });
  }
  return choices;
}

// Appareils AdGuard d'un enfant (il en est propriétaire), ids triés.
function kidAdguardResources(state, kidId) {
  return Object.entries(state?.resources ?? {})
    .filter(([, r]) => (r.owners ?? []).includes(kidId) && (r.kinds ?? [r.kind]).includes("adguard_services"))
    .map(([id]) => id)
    .sort();
}

// Services sur demande d'un enfant (réunis sur ses appareils AdGuard, plus ses services par label)
// avec leur état : débloqué si aucun de ses appareils qui le gèrent ne le bloque et si le moteur
// ne le bloque pas pour l'enfant. `exceptions` : exceptions de ce service qui visent l'enfant ou un
// de ses appareils (AdGuard ; pour un service par label, n'importe lequel de ses appareils),
// annulées lors d'une bascule ; `openedElsewhere` : une exception globale l'ouvre (bloquer
// demande alors une fermeture pour l'enfant).
export function kidServiceToggles(state, kidId, only = null) {
  const resources = kidAdguardResources(state, kidId);
  const owned = Object.entries(state?.resources ?? {})
    .filter(([, r]) => (r.owners ?? []).includes(kidId))
    .map(([id]) => id);
  const holders = new Map(); // service -> appareils qui le gèrent sur demande
  for (const id of resources) {
    for (const s of state.resources[id].on_demand ?? []) {
      if (!state.services?.[s]?.adguard) continue;
      if (!holders.has(s)) holders.set(s, []);
      holders.get(s).push(id);
    }
  }
  // Services par label qui visent l'enfant : l'état (`blocked`) est calculé pour lui par le moteur.
  const kid = state?.kids?.[kidId];
  const labelled = new Map((kid?.label_services ?? [])
    .filter((l) => (kid.on_demand ?? []).includes(l.service))
    .map((l) => [l.service, l.blocked]));
  const all = [...new Set([...holders.keys(), ...labelled.keys()])];
  const ids = Array.isArray(only) && only.length ? only.filter((s) => holders.has(s) || labelled.has(s)) : all;
  return ids.map((service) => {
    const openOnDevices = (holders.get(service) ?? [])
      .every((id) => !(state.resources[id].blocked_services ?? []).includes(service));
    const blockedForKid = labelled.get(service) === true;
    const devices = state.services?.[service]?.labels ? owned : resources;
    return {
      service,
      label: serviceLabel(service, state.services),
      icon: serviceIcon(service, state.services),
      open: openOnDevices && !blockedForKid,
      exceptions: (state.exceptions ?? [])
        .filter((e) => e.target?.service === service
          && (e.target.kid_id === kidId || devices.includes(e.target.resource_id)))
        .map((e) => e.id),
      openedElsewhere: (state.exceptions ?? []).some((e) => e.open && e.target?.service === service
        && !e.target.kid_id && !e.target.resource_id),
    };
  });
}

// Autorisations en cours qui touchent un enfant, pour ses pilules (formatPill) : libellé selon la
// cible (service, appareil, tous ses appareils), sans répéter le nom de l'enfant.
export function kidExceptions(state, kidId, hass) {
  const out = [];
  for (const e of state?.exceptions ?? []) {
    if (!e.open) continue;
    const tg = e.target ?? {};
    const resource = tg.resource_id ? state.resources?.[tg.resource_id] : null;
    if (tg.resource_id && !(resource?.owners ?? []).includes(kidId)) continue;
    if (tg.kid_id && tg.kid_id !== kidId) continue;
    // Où : l'appareil, tous ceux de l'enfant, ou tous (formatPill ajoute alors « tout le monde »).
    const where = resource ? (resource.name || tg.resource_id) : tg.kid_id ? t(hass, "exception.their_devices") : "";
    const label = tg.service
      ? [serviceLabel(tg.service, state.services), where].filter(Boolean).join(" · ")
      : where ? where.charAt(0).toUpperCase() + where.slice(1) : t(hass, "exception.all_devices");
    out.push({
      id: e.id, label, service: tg.service ?? null,
      scope: tg.resource_id || tg.kid_id ? "resource" : "all",
      kid: null, until: e.until ?? null, endsAt: e.ends_at ?? null,
    });
  }
  return out;
}

// Ce que la carte enfant montre de la journée : devoirs (plage « après devoirs » : à valider ou
// validés), minuteur (plage « quota » : en cours ou à lancer) et temps d'écran restant.
export function kidView(state, kidId) {
  const kid = state?.kids?.[kidId];
  if (!kid) return { status: Object.keys(state?.kids ?? {}).length ? "unknown" : "unavailable" };
  const remaining = kid.remaining_minutes ?? null;
  return {
    status: "ok",
    kid,
    name: kid.name || kidId,
    homework: kid.segment === "after_homework" ? (kid.status === "waiting_homework" ? "todo" : "done") : null,
    timer: kid.segment !== "quota" ? null
      : kid.timer_end ? { running: true, end: kid.timer_end }
        : { running: false, canStart: kid.status === "waiting_timer" && (remaining ?? 0) > 0 },
    remaining,
  };
}

// Heure de reprise d'une ressource fermée par la frise, que le moteur ne donne pas (`until` nul) :
// fin de segment la plus proche, seulement si tous les propriétaires sont dans un segment « blocked »
// (la frise affiche la même heure par enfant). La Switch (« sur demande ») n'a pas de reprise.
function blockedSegmentEnd(kids, owners) {
  let best = null;
  for (const id of owners ?? []) {
    const kid = kids?.[id];
    if (!kid || kid.segment !== "blocked" || !kid.segment_end) return null;
    if (best === null || new Date(kid.segment_end) < new Date(best)) best = kid.segment_end;
  }
  return best;
}

// Ligne de raison : raison du moteur, puis l'heure locale du prochain changement s'il est connu.
export function reasonLine(view, hass) {
  const parts = [];
  const reason = reasonText(view, hass);
  if (reason) parts.push(reason);
  if (view.until) {
    // le moteur met parfois déjà l'heure dans sa raison (« Écrans autorisés jusqu'à 20:00 ») ;
    // sans code (ancien moteur), on la cherche dans le texte
    const until = t(hass, "time.until", { time: formatTime(hass, view.until) });
    const repeated = view.reason_code ? view.reason_code === "allowed_until" : reason.includes(until);
    if (!repeated) parts.push(until);
  }
  else if (!view.open && view.resumesAt) parts.push(t(hass, "time.resumes", { time: formatTime(hass, view.resumesAt) }));
  return parts.join(" · ");
}

// Badge d'état d'une ressource : la pause l'emporte sur l'état ouvert/fermé.
export function stateBadge(view, hass) {
  if (view.paused) return { label: t(hass, "status.paused"), cls: "warn" };
  return view.open ? { label: t(hass, "status.allowed"), cls: "ok" } : { label: t(hass, "status.blocked"), cls: "bad" };
}

// Libellé d'une pilule bonus : « +15m », « +1h », « +1h30m ».
export function bonusLabel(minutes) {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (!h) return `+${m}m`;
  return m ? `+${h}h${String(m).padStart(2, "0")}m` : `+${h}h`;
}

const DEFAULT_BONUS = [15, 30, 60];

// Durées des pilules bonus : `bonus_minutes` de la config si elle contient des entiers > 0, sinon 15/30/60.
export function bonusMinutes(config) {
  const list = config?.bonus_minutes;
  if (!Array.isArray(list)) return DEFAULT_BONUS;
  const valid = list.map(Number).filter((m) => Number.isInteger(m) && m > 0);
  return valid.length ? valid : DEFAULT_BONUS;
}

// Valeur numérique (minutes) d'une entité de `hass.states` ; absente ou non numérique -> 0.
const entityMinutes = (hass, entityId) => {
  const n = parseFloat(hass?.states?.[entityId]?.state);
  return Number.isFinite(n) ? n : 0;
};

// Jauge de la carte Switch : accordé = utilisé + restant ; `pct` = restant / accordé (0 si rien d'accordé).
export function switchGauge(hass, view) {
  const used = entityMinutes(hass, view.nintendo?.used_entity);
  const remaining = entityMinutes(hass, view.nintendo?.remaining_entity);
  const granted = used + remaining;
  return {
    used, remaining, granted,
    pct: granted > 0 ? Math.max(0, Math.min(100, (remaining / granted) * 100)) : 0,
  };
}

// Barre « utilisé / autorisé » (autorisé = utilisé + restant) ; null si la ressource n'a pas de quota.
export function quotaBar(view, hass) {
  // sans temps restant, la ressource n'a pas de quota du jour
  if (view.remaining == null) return null;
  const used = view.used ?? 0;
  const total = used + (view.remaining ?? 0);
  return {
    pct: total > 0 ? Math.min(100, (used / total) * 100) : 0,
    text: `${fmtDuration(used, hass)} / ${fmtDuration(total, hass)}`,
    over: total > 0 && used >= total,
  };
}

// Projette les segments ISO sur 0-100 % de la journée locale de `now`.
export function timelineGeometry(segments, now) {
  const day0 = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const day1 = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
  const span = day1 - day0;
  const pct = (d) => Math.min(100, Math.max(0, ((d - day0) / span) * 100));
  const bars = [];
  for (const s of segments ?? []) {
    const left = pct(new Date(s.start));
    const width = pct(new Date(s.end)) - left;
    if (width > 0) bars.push({ left, width, type: s.type });
  }
  return { bars, nowPct: pct(now) };
}

// Libellé du type de jour du moteur ; type inconnu affiché tel quel, absent -> chaîne vide.
export function dayTypeLabel(type, hass) {
  if (!type) return "";
  return hasKey(`daytype.${type}`) ? t(hass, `daytype.${type}`) : String(type);
}

// Classe de couleur d'un segment de la frise ; un type inconnu est traité comme bloqué.
export function segmentClass(type) {
  return ["free", "after_homework", "quota", "on_demand"].includes(type) ? type : "blocked";
}

// Classe de couleur du statut d'un enfant (texte de statut dans la frise).
export function statusClass(status) {
  if (status === "allowed") return "ok";
  if (["waiting_homework", "waiting_timer", "on_demand", "paused"].includes(status)) return "warn";
  return "bad";
}

// Capteur « Statut » d'un enfant (`status_entity` de l'instantané, lu par le serveur dans le
// registre des entités) s'il existe dans HA ; sinon null (pas de toucher sur la frise).
export function statusEntity(kid, hass) {
  const entityId = kid?.status_entity;
  return entityId && hass?.states?.[entityId] ? entityId : null;
}

// Prochaine étape d'un enfant : « reprise HH:MM » s'il est bloqué, « jusqu'à HH:MM » s'il est libre ;
// chaîne vide sans fin de segment.
export function nextStepLabel(kid, hass) {
  if (!kid?.segment_end) return "";
  const open = kid.status === "allowed" || kid.status === "on_demand";
  return t(hass, open ? "time.until" : "time.resumes", { time: formatTime(hass, kid.segment_end) });
}

// Plages hachurées (en % de la journée locale de `now`) des exceptions ouvertes : de `now` à `endsAt`,
// ou jusqu'à la fin de la journée sans `endsAt` ; les plages vides ou déjà passées sont écartées.
export function exceptionSpans(exceptions, now) {
  const dayEnd = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
  const spans = [];
  for (const e of exceptions ?? []) {
    const end = e.endsAt ? new Date(e.endsAt) : dayEnd;
    const { bars } = timelineGeometry([{ start: now.toISOString(), end: end.toISOString(), type: "exception" }], now);
    if (bars[0]) spans.push({ id: e.id, left: bars[0].left, width: bars[0].width });
  }
  return spans;
}

// Faut-il (ré)essayer la souscription ? Non sans connexion, si elle est déjà faite pour cette
// connexion, ou si elle vient d'y échouer (seul le tick de 60 s réessaie, pas chaque `hass`).
export function shouldSubscribe(conn, subConn, failedConn) {
  return !!conn && subConn !== conn && failedConn !== conn;
}

// Saisie au pavé numérique du code parent (4 à 8 chiffres) : chiffre ajouté, « back » efface le
// dernier, « clear » vide ; toute autre touche est ignorée.
const CODE_MAX = 8;
export function keypadInput(value, key) {
  if (key === "back") return value.slice(0, -1);
  if (key === "clear") return "";
  if (/^\d$/.test(key) && value.length < CODE_MAX) return value + key;
  return value;
}

// Pastille d'en-tête des cartes : rappelle que le moteur simule sans rien piloter.
export function simulationBadge(state, hass) {
  return state?.simulation ? `<span class="sim">${esc(t(hass, "common.simulation"))}</span>` : "";
}
