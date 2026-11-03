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
  { value: "media_player", label: "Lecteur multimédia (télé, Google TV, Chromecast…)", options: ["entity_id"] },
  { value: "switch", label: "Interrupteur (prise, écran de PC…)", options: ["entity_id"] },
  { value: "adguard_services", label: "Client AdGuard", options: ["device_id"] },
  { value: "nintendo", label: "Console Nintendo", options: ["device_id", "limit_entity", "remaining_entity", "used_entity"] },
];

// Noms lisibles des intégrations HA les plus courantes ; les autres gardent leur identifiant.
const PLATFORM_LABELS = {
  androidtv_remote: "Android TV Remote", androidtv: "Android TV", cast: "Google Cast",
  samsungtv: "Samsung TV", smartthings: "SmartThings", webostv: "LG webOS", braviatv: "Sony Bravia",
  apple_tv: "Apple TV", roku: "Roku", shelly: "Shelly", tplink: "TP-Link", tuya: "Tuya",
  zha: "Zigbee (ZHA)", mqtt: "MQTT", esphome: "ESPHome", hue: "Philips Hue", template: "Modèle",
};

// Entités d'un domaine (« media_player », « switch ») pour une liste de choix : libellé
// « nom de l'appareil — intégration », trié ; l'appareil manque si l'entité n'en a pas.
export function entityChoices(hass, domain) {
  const prefix = `${domain}.`;
  return Object.keys(hass?.states ?? {})
    .filter((id) => id.startsWith(prefix))
    .map((id) => {
      const entry = hass.entities?.[id];
      const device = entry?.device_id ? hass.devices?.[entry.device_id] : null;
      const name = hass.states[id].attributes?.friendly_name
        || device?.name_by_user || device?.name || id;
      const platform = entry?.platform ? PLATFORM_LABELS[entry.platform] ?? entry.platform : null;
      return { value: id, label: platform ? `${name} — ${platform}` : name };
    })
    .sort((a, b) => a.label.localeCompare(b.label, "fr"));
}

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

// Brouillon d'une nouvelle installation (aucune config enregistrée) : au format v2, celui que
// produisent `addResource`/`addIntegration`.
export function emptyConfig() {
  return { version: 2, default_leisure: [], calendar_map: {}, notify: [], kids: [], resources: [] };
}

// Ressource au format v2 (appareils physiques) ? Une ressource v1 collée dans l'onglet JSON n'en
// a pas : le moteur la convertit à l'enregistrement.
export function hasDevices(resource) {
  return Array.isArray(resource?.devices);
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

// Nouvelle ressource : un appareil physique vide, à compléter par des intégrations.
export function addResource(cfg, name) {
  const id = uniqueId(slugify(name), cfg.resources.map((r) => r.id));
  const res = { id, name: name || id, owners: [], quota_minutes: {}, devices: [{ name: name || id, integrations: [] }] };
  cfg.resources.push(res);
  return res;
}

export function addDevice(resource, name) {
  const device = { name, integrations: [] };
  resource.devices.push(device);
  return device;
}

export function removeDevice(resource, index) {
  resource.devices.splice(index, 1);
}

// Intégration aux options vides, selon le type.
export function addIntegration(device, kind) {
  const spec = KINDS.find((k) => k.value === kind) ?? KINDS[0];
  const integration = { kind: spec.value };
  for (const opt of spec.options) integration[opt] = "";
  device.integrations.push(integration);
  return integration;
}

export function removeIntegration(device, index) {
  device.integrations.splice(index, 1);
}

const kindsOf = (resource) => resource.devices.flatMap((d) => d.integrations.map((i) => i.kind));

// Types ajoutables à la ressource : une Nintendo doit rester seule dans sa ressource.
export function integrationKindsAllowed(resource) {
  const kinds = kindsOf(resource);
  if (kinds.includes("nintendo")) return [];
  const all = KINDS.map((k) => k.value);
  return kinds.length ? all.filter((k) => k !== "nintendo") : all;
}

// Déplace un appareil physique vers une autre ressource (ajouté à la fin). Si la source se vide,
// elle est retirée (modes compris) et son id est renvoyé.
export function moveDevice(cfg, fromIndex, deviceIndex, toIndex) {
  const source = cfg.resources[fromIndex];
  const target = cfg.resources[toIndex];
  if (!source || !target || fromIndex === toIndex) return null;
  const [device] = source.devices.splice(deviceIndex, 1);
  if (!device) return null;
  target.devices.push(device);
  if (source.devices.length) return null;
  removeResource(cfg, fromIndex);
  return source.id;
}

// Index des ressources où l'appareil physique peut aller sans casser la règle « une Nintendo reste
// seule » : un appareil avec Nintendo ne va que dans une ressource sans intégration, les autres
// jamais dans une ressource Nintendo.
export function moveTargets(cfg, fromIndex, deviceIndex) {
  const device = cfg.resources[fromIndex]?.devices[deviceIndex];
  if (!device) return [];
  const nintendo = device.integrations.some((i) => i.kind === "nintendo");
  return cfg.resources.flatMap((r, i) => {
    if (i === fromIndex) return [];
    const kinds = kindsOf(r);
    return (nintendo ? !kinds.length : !kinds.includes("nintendo")) ? [i] : [];
  });
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
