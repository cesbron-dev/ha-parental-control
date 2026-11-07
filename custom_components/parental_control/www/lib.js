// Bibliothèque partagée des cartes Contrôle parental : fonctions pures, sans DOM.

const SERVICES = {
  youtube: "YouTube",
  tiktok: "TikTok",
  disneyplus: "Disney+",
  netflix: "Netflix",
  roblox: "Roblox",
  twitch: "Twitch",
  snapchat: "Snapchat",
  instagram: "Instagram",
  discord: "Discord",
  fortnite: "Fortnite",
  reddit: "Reddit",
  facebook: "Facebook",
};

const pad = (n) => String(n).padStart(2, "0");

// Heure locale « HH:MM » d'une date ISO.
const hhmm = (iso) => {
  const d = new Date(iso);
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
};

// Échappe un texte venant du moteur avant de l'insérer dans du HTML.
export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);
}

// Durée en minutes -> « 1h 05m » (négatif ou invalide -> « 0h 00m »).
export function fmtDuration(minutes) {
  const total = Math.max(0, Math.round(Number(minutes) || 0));
  return `${Math.floor(total / 60)}h ${pad(total % 60)}m`;
}

export function serviceLabel(id) {
  if (SERVICES[id]) return SERVICES[id];
  const s = String(id ?? "");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

// Le compte non admin doit saisir le code parent pour ouvrir (open, bonus, devoirs, minuteur),
// pas pour fermer.
export function needsCode(hass, action) {
  if (hass?.user?.is_admin) return false;
  return ["open", "bonus", "homework", "timer"].includes(action);
}

// Un compte non admin peut envoyer une demande de temps quand le moteur l'a activée.
export function canRequest(hass, state) {
  return !hass?.user?.is_admin && !!state?.requests_enabled;
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
function requestDuration(minutes) {
  if (minutes == null) return "jusqu'au prochain changement";
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (!h) return `${m} min`;
  return m ? `${h} h ${pad(m)}` : `${h} h`;
}

// Ligne d'état d'une demande, affichée sous les pastilles de la carte.
export function requestLine(req) {
  switch (req.status) {
    case "pending": return "Demande envoyée · en attente";
    case "accepted": return req.kind === "homework" ? "Accepté" : `Accepté : ${requestDuration(req.granted)}`;
    case "refused": return "Refusé";
    case "expired": return "Pas de réponse";
    default: return `Impossible : ${req.reason ?? ""}`;
  }
}

function scopeOf(target) {
  if (target.resource_id) return "resource";
  if (target.kid_id) return "kid";
  return "all";
}

// Exceptions ouvertes qui touchent une ressource (cible ressource, enfant propriétaire ou globale).
export function exceptionsForResource(state, resourceId) {
  const resource = state?.resources?.[resourceId];
  if (!resource) return [];
  const out = [];
  for (const e of state.exceptions ?? []) {
    if (!e.open) continue;
    const t = e.target ?? {};
    const touches = t.resource_id
      ? t.resource_id === resourceId
      : t.kid_id
        ? (resource.owners ?? []).includes(t.kid_id)
        : true;
    if (!touches) continue;
    // Une exception de service ne concerne que les appareils qui ont une intégration AdGuard.
    if (t.service && !(resource.kinds ?? [resource.kind]).includes("adguard_services")) continue;
    const scope = scopeOf(t);
    out.push({
      id: e.id,
      label: t.service ? serviceLabel(t.service) : "Tout l'appareil",
      service: t.service ?? null,
      scope,
      kid: scope === "kid" ? (state.kids?.[t.kid_id]?.name ?? t.kid_id) : null,
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
    const t = e.target ?? {};
    const touches = t.resource_id
      ? (state.resources?.[t.resource_id]?.owners ?? []).includes(kidId)
      : t.kid_id
        ? t.kid_id === kidId
        : true;
    if (touches) out.push({ id: e.id, endsAt: e.ends_at ?? null, scope: scopeOf(t) });
  }
  return out;
}

// Durée restante en minutes arrondies au-dessus : « 42 min », « 1 h 15 ».
function fmtRemaining(ms) {
  const m = Math.max(0, Math.ceil(ms / 60000));
  return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${pad(m % 60)}`;
}

export function formatPill(exc, now) {
  let when;
  if (exc.until) {
    when = fmtRemaining(new Date(exc.until) - now);
  } else if (exc.endsAt) {
    when = `jusqu'à ${hhmm(exc.endsAt)}`;
  } else {
    when = "jusqu'à nouvel ordre";
  }
  let text = `${exc.label} · ${when}`;
  if (exc.scope === "kid") text += ` · ${exc.kid} · tous ses appareils`;
  else if (exc.scope === "all") text += " · tout le monde";
  return text;
}

// Vue d'une ressource pour l'affichage ; `status` distingue moteur sans snapshot et ressource inconnue.
export function resourceView(state, resourceId) {
  const resources = state?.resources ?? {};
  const base = {
    status: "ok", name: null, kind: null, kinds: [], icon: null, owners: [], open: false, reason: "", until: null,
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
// non, d'après `blocked_services` du moteur). `only` (liste
// d'ids, config de la carte) restreint et ordonne l'affichage. `exceptions` : ids des exceptions
// de ce service posées sur cet appareil (à remplacer lors d'une bascule, pour ne pas les empiler).
export function serviceToggles(state, resourceId, only = null) {
  const r = state?.resources?.[resourceId];
  if (!r || !(r.kinds ?? [r.kind]).includes("adguard_services")) return [];
  const onDemand = r.on_demand ?? [];
  const ids = Array.isArray(only) && only.length ? only.filter((s) => onDemand.includes(s)) : onDemand;
  const blocked = new Set(r.blocked_services ?? []);
  return ids.map((service) => ({
    service,
    label: serviceLabel(service),
    open: !blocked.has(service),
    exceptions: (state.exceptions ?? [])
      .filter((e) => e.target?.resource_id === resourceId && e.target?.service === service)
      .map((e) => e.id),
    // Ouvert par une exception d'enfant ou globale : le bloquer demande une fermeture, pas
    // seulement d'annuler les exceptions de cet appareil.
    openedElsewhere: exceptionsForResource(state, resourceId).some((e) => e.service === service && e.scope !== "resource"),
  }));
}

// Appareils AdGuard d'un enfant (il en est propriétaire), ids triés.
function kidAdguardResources(state, kidId) {
  return Object.entries(state?.resources ?? {})
    .filter(([, r]) => (r.owners ?? []).includes(kidId) && (r.kinds ?? [r.kind]).includes("adguard_services"))
    .map(([id]) => id)
    .sort();
}

// Services sur demande d'un enfant (réunis sur ses appareils AdGuard) avec leur état : débloqué si
// aucun de ses appareils qui le gèrent ne le bloque. `exceptions` : exceptions de ce service qui
// visent l'enfant ou un de ses appareils (annulées lors d'une bascule) ; `openedElsewhere` : une
// exception globale l'ouvre (bloquer demande alors une fermeture pour l'enfant).
export function kidServiceToggles(state, kidId, only = null) {
  const resources = kidAdguardResources(state, kidId);
  const holders = new Map(); // service -> appareils qui le gèrent sur demande
  for (const id of resources) {
    for (const s of state.resources[id].on_demand ?? []) {
      if (!holders.has(s)) holders.set(s, []);
      holders.get(s).push(id);
    }
  }
  const all = [...holders.keys()];
  const ids = Array.isArray(only) && only.length ? only.filter((s) => holders.has(s)) : all;
  return ids.map((service) => ({
    service,
    label: serviceLabel(service),
    open: holders.get(service).every((id) => !(state.resources[id].blocked_services ?? []).includes(service)),
    exceptions: (state.exceptions ?? [])
      .filter((e) => e.target?.service === service
        && (e.target.kid_id === kidId || resources.includes(e.target.resource_id)))
      .map((e) => e.id),
    openedElsewhere: (state.exceptions ?? []).some((e) => e.open && e.target?.service === service
      && !e.target.kid_id && !e.target.resource_id),
  }));
}

// Autorisations en cours qui touchent un enfant, pour ses pilules (formatPill) : libellé selon la
// cible (service, appareil, tous ses appareils), sans répéter le nom de l'enfant.
export function kidExceptions(state, kidId) {
  const out = [];
  for (const e of state?.exceptions ?? []) {
    if (!e.open) continue;
    const t = e.target ?? {};
    const resource = t.resource_id ? state.resources?.[t.resource_id] : null;
    if (t.resource_id && !(resource?.owners ?? []).includes(kidId)) continue;
    if (t.kid_id && t.kid_id !== kidId) continue;
    // Où : l'appareil, tous ceux de l'enfant, ou tous (formatPill ajoute alors « tout le monde »).
    const where = resource ? (resource.name || t.resource_id) : t.kid_id ? "tous ses appareils" : "";
    const label = t.service
      ? [serviceLabel(t.service), where].filter(Boolean).join(" · ")
      : where ? where.charAt(0).toUpperCase() + where.slice(1) : "Tous les appareils";
    out.push({
      id: e.id, label, service: t.service ?? null,
      scope: t.resource_id || t.kid_id ? "resource" : "all",
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
    homework: kid.segment === "apres_devoirs" ? (kid.status === "attente_devoirs" ? "todo" : "done") : null,
    timer: kid.segment !== "quota" ? null
      : kid.timer_end ? { running: true, end: kid.timer_end }
        : { running: false, canStart: kid.status === "attente_minuteur" && (remaining ?? 0) > 0 },
    remaining,
  };
}

// Heure de reprise d'une ressource fermée par la frise, que le moteur ne donne pas (`until` nul) :
// fin de segment la plus proche, seulement si tous les propriétaires sont dans un segment « bloque »
// (la frise affiche la même heure par enfant). La Switch (« sur demande ») n'a pas de reprise.
function blockedSegmentEnd(kids, owners) {
  let best = null;
  for (const id of owners ?? []) {
    const kid = kids?.[id];
    if (!kid || kid.segment !== "bloque" || !kid.segment_end) return null;
    if (best === null || new Date(kid.segment_end) < new Date(best)) best = kid.segment_end;
  }
  return best;
}

// Ligne de raison : raison du moteur, puis l'heure locale du prochain changement s'il est connu.
export function reasonLine(view) {
  const parts = [];
  if (view.reason) parts.push(view.reason);
  // le moteur met parfois déjà l'heure dans sa raison (« Écrans autorisés jusqu'à 20:00 »)
  if (view.until) {
    const until = `jusqu'à ${hhmm(view.until)}`;
    if (!view.reason?.includes(until)) parts.push(until);
  }
  else if (!view.open && view.resumesAt) parts.push(`reprise ${hhmm(view.resumesAt)}`);
  return parts.join(" · ");
}

// Badge d'état d'une ressource : la pause l'emporte sur l'état ouvert/fermé.
export function stateBadge(view) {
  if (view.paused) return { label: "Pause", cls: "warn" };
  return view.open ? { label: "Autorisé", cls: "ok" } : { label: "Bloqué", cls: "bad" };
}

// Libellé d'une pilule bonus : « +15m », « +1h », « +1h30m ».
export function bonusLabel(minutes) {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (!h) return `+${m}m`;
  return m ? `+${h}h${pad(m)}m` : `+${h}h`;
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
export function quotaBar(view) {
  // sans temps restant, la ressource n'a pas de quota du jour
  if (view.remaining == null) return null;
  const used = view.used ?? 0;
  const total = used + (view.remaining ?? 0);
  return {
    pct: total > 0 ? Math.min(100, (used / total) * 100) : 0,
    text: `${fmtDuration(used)} / ${fmtDuration(total)}`,
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

const DAY_TYPES = {
  ecole: "Jour d'école",
  fin_de_semaine: "Fin de semaine",
  conge_peda: "Congé pédago",
  vacances: "Vacances",
};

// Libellé du type de jour du moteur ; type inconnu affiché tel quel, absent -> chaîne vide.
export function dayTypeLabel(type) {
  return DAY_TYPES[type] ?? (type ? String(type) : "");
}

// Classe de couleur d'un segment de la frise ; un type inconnu est traité comme bloqué.
export function segmentClass(type) {
  return ["libre", "apres_devoirs", "quota", "sur_demande"].includes(type) ? type : "bloque";
}

// Classe de couleur du statut d'un enfant (texte de statut dans la frise).
export function statusClass(status) {
  if (status === "autorise") return "ok";
  if (["attente_devoirs", "attente_minuteur", "sur_demande", "pause"].includes(status)) return "warn";
  return "bad";
}

// Prochaine étape d'un enfant : « reprise HH:MM » s'il est bloqué, « jusqu'à HH:MM » s'il est libre ;
// chaîne vide sans fin de segment.
export function nextStepLabel(kid) {
  if (!kid?.segment_end) return "";
  const open = kid.status === "autorise" || kid.status === "sur_demande";
  return `${open ? "jusqu'à" : "reprise"} ${hhmm(kid.segment_end)}`;
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
export function simulationBadge(state) {
  return state?.simulation ? '<span class="sim">SIMULATION</span>' : "";
}
