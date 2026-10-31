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

// Le compte non admin doit saisir le code parent pour ouvrir (open, bonus), pas pour fermer.
export function needsCode(hass, action) {
  if (hass?.user?.is_admin) return false;
  return action === "open" || action === "bonus";
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
    // Une exception de service ne concerne que les ressources AdGuard.
    if (t.service && resource.kind !== "adguard_services") continue;
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
    status: "ok", name: null, kind: null, owners: [], open: false, reason: "", until: null,
    used: null, remaining: null, leisure: [], nintendo: null, paused: !!state?.paused, resumesAt: null,
  };
  if (Object.keys(resources).length === 0) return { ...base, status: "unavailable" };
  const r = resources[resourceId];
  if (!r) return { ...base, status: "unknown" };
  return {
    ...base,
    name: r.name,
    kind: r.kind,
    owners: r.owners ?? [],
    open: !!r.open,
    reason: r.reason ?? "",
    until: r.until ?? null,
    used: r.used_minutes ?? null,
    remaining: r.remaining_minutes ?? null,
    leisure: r.leisure ?? [],
    nintendo: r.kind === "nintendo"
      ? { used_entity: r.used_entity, remaining_entity: r.remaining_entity }
      : null,
    resumesAt: r.kind === "nintendo" ? null : blockedSegmentEnd(state.kids, r.owners),
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
  if (view.until) parts.push(`jusqu'à ${hhmm(view.until)}`);
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
