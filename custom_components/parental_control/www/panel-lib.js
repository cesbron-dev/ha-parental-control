// Logique pure du panneau « Règles » : édition en place du brouillon de configuration (même forme
// que `parental_control/config/get`), sans DOM. Le moteur reste seul juge de la validité (config/set).

export const DAY_TYPES = [
  { value: "ecole", label: "École", required: true },
  { value: "fin_de_semaine", label: "Fin de semaine", required: true },
  { value: "conge_peda", label: "Congé pédagogique", required: false },
  { value: "vacances", label: "Vacances", required: false },
];
export const SEGMENT_TYPES = [
  { value: "bloque", label: "Bloqué" },
  { value: "libre", label: "Libre" },
  { value: "apres_devoirs", label: "Après devoirs" },
  { value: "quota", label: "Quota" },
  { value: "sur_demande", label: "Sur demande" },
];
export const MODES = [
  { value: "suit_frise", label: "Suit la frise" },
  { value: "sur_demande", label: "Sur demande" },
  { value: "bloque", label: "Bloqué" },
  { value: "libre", label: "Libre" },
];
export const KINDS = [
  { value: "media_player", label: "Télé (lecteur multimédia)", options: ["entity_id"] },
  { value: "adguard_services", label: "Client AdGuard", options: ["device_id"] },
  { value: "nintendo", label: "Console Nintendo", options: ["device_id", "limit_entity", "remaining_entity", "used_entity"] },
];

const BLOCKED_DAY = () => ({ segments: [{ start: "00:00", type: "bloque" }] });
const clone = (v) => JSON.parse(JSON.stringify(v));

// Identifiant tiré d'un nom : minuscules, sans accents, mots reliés par `_`.
export function slugify(name) {
  return String(name ?? "")
    .normalize("NFD").replace(/[̀-ͯ]/g, "")
    .toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
}

export function uniqueId(base, existing) {
  const root = base || "element";
  if (!existing.includes(root)) return root;
  for (let i = 2; ; i++) if (!existing.includes(`${root}_${i}`)) return `${root}_${i}`;
}

// Écrit `value` au chemin `a.0.b` (créant les objets manquants). Texte vide -> null ; null ou
// undefined sur un quota ou des minutes d'avertissement -> clé retirée (valeur par défaut du moteur).
export function setPath(obj, path, value) {
  const keys = path.split(".");
  let node = obj;
  for (const k of keys.slice(0, -1)) {
    if (node[k] === undefined || node[k] === null) node[k] = {};
    node = node[k];
  }
  const last = keys[keys.length - 1];
  const optionalNumber = last === "warn_minutes" || keys.includes("quota_minutes");
  if ((value === null || value === undefined) && optionalNumber) {
    delete node[last];
    return;
  }
  node[last] = value === "" ? null : value;
}

export function addKid(cfg, name) {
  const id = uniqueId(slugify(name), cfg.kids.map((k) => k.id));
  const profiles = cfg.kids.length
    ? clone(cfg.kids[0].profiles)
    : { ecole: BLOCKED_DAY(), fin_de_semaine: BLOCKED_DAY() };
  const kid = {
    id, name: name || id, emoji: null, color: null, calendar: null,
    leisure_add: [], leisure_remove: [], resource_modes: {}, profiles,
  };
  cfg.kids.push(kid);
  return kid;
}

// Retire l'enfant et ses mentions comme propriétaire (sinon le moteur refuse la config).
export function removeKid(cfg, index) {
  const [kid] = cfg.kids.splice(index, 1);
  if (!kid) return;
  for (const r of cfg.resources) r.owners = r.owners.filter((o) => o !== kid.id);
}

export function addResource(cfg, kind, name) {
  const id = uniqueId(slugify(name), cfg.resources.map((r) => r.id));
  const spec = KINDS.find((k) => k.value === kind) ?? KINDS[0];
  const res = { id, name: name || id, kind: spec.value, owners: [], quota_minutes: {} };
  for (const opt of spec.options) res[opt] = "";
  cfg.resources.push(res);
  return res;
}

// Retire l'appareil et les modes qui le citent (sinon le moteur refuse la config).
export function removeResource(cfg, index) {
  const [res] = cfg.resources.splice(index, 1);
  if (!res) return;
  for (const kid of cfg.kids) delete kid.resource_modes[res.id];
}

const toMinutes = (hhmm) => {
  const m = /^(\d{1,2}):(\d{2})$/.exec(String(hhmm ?? ""));
  if (!m) return null;
  const v = Number(m[1]) * 60 + Number(m[2]);
  return v >= 0 && v < 24 * 60 ? v : null;
};
const toHHMM = (minutes) => `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;

// Nouveau segment une heure après le dernier (au plus 23:59), bloqué par défaut.
export function addSegment(segments) {
  const last = toMinutes(segments[segments.length - 1]?.start) ?? 0;
  segments.push({ start: toHHMM(Math.min(last + 60, 23 * 60 + 59)), type: "bloque" });
}

// Le premier segment (00:00) est obligatoire : il ne se supprime pas.
export function removeSegment(segments, index) {
  if (index > 0 && index < segments.length) segments.splice(index, 1);
}

// « Suit la frise » est le défaut du moteur : pas d'entrée.
export function setMode(kid, resourceId, mode) {
  if (mode === "suit_frise") delete kid.resource_modes[resourceId];
  else kid.resource_modes[resourceId] = mode;
}

export function toggleListValue(list, value) {
  const i = list.indexOf(value);
  if (i >= 0) list.splice(i, 1);
  else list.push(value);
}

export function toggleOwner(resource, kidId) {
  toggleListValue(resource.owners, kidId);
}

// Congé pédagogique et vacances : profil propre (copie de la fin de semaine) ou absent.
export function toggleProfile(kid, day) {
  if (DAY_TYPES.find((d) => d.value === day)?.required !== false) return;
  if (day in kid.profiles) delete kid.profiles[day];
  else kid.profiles[day] = clone(kid.profiles.fin_de_semaine ?? BLOCKED_DAY());
}

// Aperçu d'une frise : segments en % de la journée ; les heures invalides sont ignorées.
export function profileGeometry(segments) {
  const valid = (segments ?? [])
    .map((s) => ({ start: toMinutes(s.start), type: s.type }))
    .filter((s) => s.start !== null);
  return valid.map((s, i) => {
    const end = i + 1 < valid.length ? valid[i + 1].start : 24 * 60;
    return { left: (s.start / 1440) * 100, width: (Math.max(0, end - s.start) / 1440) * 100, type: s.type };
  });
}

export function isDirty(original, draft) {
  return JSON.stringify(original) !== JSON.stringify(draft);
}
