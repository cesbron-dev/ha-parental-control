// Logique pure du panneau « Règles » : édition en place du brouillon de configuration (même forme
// que `parental_control/config/get`), sans DOM. Le moteur reste seul juge de la validité (config/set).
// Les fonctions qui produisent un texte prennent `hass` (langue de l'utilisateur, anglais sans lui).
import { t, lang, errorText } from "./i18n.js";

const ucfirst = (text) => text.charAt(0).toUpperCase() + text.slice(1);
// « 1 intégration », « 2 intégrations » : clés `<key>_one` et `<key>_other`, règle de la langue.
const plural = (hass, key, count) => {
  const form = new Intl.PluralRules(lang(hass)).select(count) === "one" ? "one" : "other";
  return t(hass, `${key}_${form}`, { count });
};

export const DAY_TYPES = [
  { value: "school", required: true },
  { value: "weekend", required: true },
  { value: "day_off", required: false },
  { value: "holidays", required: false },
];
export const SEGMENT_TYPES = [
  { value: "blocked" }, { value: "free" }, { value: "after_homework" }, { value: "quota" }, { value: "on_demand" },
];
export const MODES = [{ value: "schedule" }, { value: "on_demand" }, { value: "blocked" }, { value: "free" }];
export const KINDS = [
  { value: "media_player", options: ["entity_id"] },
  { value: "switch", options: ["entity_id"] },
  { value: "adguard_services", options: ["device_id"] },
  { value: "nintendo", options: ["device_id", "limit_entity", "remaining_entity", "used_entity"] },
];

// Listes ci-dessus avec leurs libellés dans la langue de l'utilisateur.
export function dayTypes(hass) {
  return DAY_TYPES.map((d) => ({ ...d, label: t(hass, `daytype.${d.value}`), short: t(hass, `panel.daytype_short.${d.value}`) }));
}
export function segmentTypes(hass) {
  return SEGMENT_TYPES.map((s) => ({ ...s, label: ucfirst(t(hass, `segment.${s.value}`)) }));
}
export function modes(hass) {
  return MODES.map((m) => ({ ...m, label: t(hass, `panel.mode.${m.value}`), short: t(hass, `panel.mode_short.${m.value}`) }));
}
export function kinds(hass) {
  return KINDS.map((k) => ({ ...k, label: t(hass, `panel.kind.${k.value}`), short: t(hass, `panel.kind_short.${k.value}`) }));
}

// Erreur de `config/set` : `invalid_config` traduite d'après `translation_key` (`config_<code>` ->
// `config_error.<code>`) et `translation_placeholders` (dont `path`) ; les autres erreurs par
// `errorText` (erreur d'action, code WebSocket), sinon le message du serveur.
export function configErrorText(hass, err) {
  if (err === null || err === undefined) return "";
  if (typeof err !== "object") return String(err);
  const key = String(err.translation_key ?? "");
  const catalogueKey = `config_error.${key.slice("config_".length)}`;
  if (key.startsWith("config_") && t(hass, catalogueKey) !== catalogueKey) {
    return t(hass, catalogueKey, err.translation_placeholders ?? {});
  }
  return errorText(hass, err);
}

// Noms lisibles des intégrations HA les plus courantes ; les autres gardent leur identifiant.
const PLATFORM_LABELS = {
  androidtv_remote: "Android TV Remote", androidtv: "Android TV", cast: "Google Cast",
  samsungtv: "Samsung TV", smartthings: "SmartThings", webostv: "LG webOS", braviatv: "Sony Bravia",
  apple_tv: "Apple TV", roku: "Roku", shelly: "Shelly", tplink: "TP-Link", tuya: "Tuya",
  zha: "Zigbee (ZHA)", mqtt: "MQTT", esphome: "ESPHome", hue: "Philips Hue",
};
const platformLabel = (hass, platform) => {
  if (!platform) return null;
  if (platform === "template") return t(hass, "panel.platform_template");
  return PLATFORM_LABELS[platform] ?? platform;
};

// Entités d'un domaine (« media_player », « switch ») pour une liste de choix : libellé
// « nom — intégration », trié. Sont exclues les entités du contrôle parental lui-même (sa pause)
// et les entités de configuration ou de diagnostic (réglages d'AdGuard, etc.).
export function entityChoices(hass, domain) {
  const prefix = `${domain}.`;
  return Object.keys(hass?.states ?? {})
    .filter((id) => id.startsWith(prefix))
    .filter((id) => {
      const entry = hass.entities?.[id];
      return entry?.platform !== "parental_control" && !entry?.entity_category;
    })
    .map((id) => {
      const entry = hass.entities?.[id];
      const device = entry?.device_id ? hass.devices?.[entry.device_id] : null;
      const name = hass.states[id].attributes?.friendly_name
        || device?.name_by_user || device?.name || id;
      const platform = platformLabel(hass, entry?.platform);
      return { value: id, label: platform ? `${name} — ${platform}` : name };
    })
    .sort((a, b) => a.label.localeCompare(b.label, lang(hass)));
}

const BLOCKED_DAY = () => ({ segments: [{ start: "00:00", type: "blocked" }] });
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
  return { version: 3, default_leisure: [], default_on_demand: [], calendar_map: {}, notify: [], request_notify: [], request_notify_owners: {}, kids: [], resources: [] };
}

// Ressource avec son arbre d'appareils physiques ? Un JSON mal formé collé dans l'onglet JSON peut
// ne pas en avoir : le moteur le refusera à l'enregistrement.
export function hasDevices(resource) {
  return Array.isArray(resource?.devices);
}

export function addKid(cfg, name) {
  const id = uniqueId(slugify(name), cfg.kids.map((k) => k.id));
  const profiles = cfg.kids.length
    ? clone(cfg.kids[0].profiles)
    : { school: BLOCKED_DAY(), weekend: BLOCKED_DAY() };
  const kid = {
    id, name: name || id, emoji: null, color: null, calendar: null,
    leisure_add: [], leisure_remove: [], on_demand_add: [], on_demand_remove: [], resource_modes: {}, profiles,
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

const kindsOf = (resource) => (hasDevices(resource)
  ? resource.devices.flatMap((d) => d.integrations?.map((i) => i.kind) ?? [])
  : []);

// Types ajoutables à la ressource : une Nintendo doit rester seule dans sa ressource ; rien dans une
// ressource sans arbre d'appareils.
export function integrationKindsAllowed(resource) {
  if (!hasDevices(resource)) return [];
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
  if (!hasDevices(source) || !hasDevices(target) || fromIndex === toIndex) return null;
  const [device] = source.devices.splice(deviceIndex, 1);
  if (!device) return null;
  target.devices.push(device);
  if (source.devices.length) return null;
  removeResource(cfg, fromIndex);
  return source.id;
}

// Index des ressources où l'appareil physique peut aller sans casser la règle « une Nintendo reste
// seule » : un appareil avec Nintendo ne va que dans une ressource sans intégration, les autres
// jamais dans une ressource Nintendo ; jamais vers ni depuis une ressource v1.
export function moveTargets(cfg, fromIndex, deviceIndex) {
  const source = cfg.resources[fromIndex];
  const device = hasDevices(source) ? source.devices[deviceIndex] : null;
  if (!device) return [];
  const nintendo = (device.integrations ?? []).some((i) => i.kind === "nintendo");
  return cfg.resources.flatMap((r, i) => {
    if (i === fromIndex || !hasDevices(r)) return [];
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
  segments.push({ start: toHHMM(Math.min(last + 60, 23 * 60 + 59)), type: "blocked" });
}

// Le premier segment (00:00) est obligatoire : il ne se supprime pas.
export function removeSegment(segments, index) {
  if (index > 0 && index < segments.length) segments.splice(index, 1);
}

// « Suit la frise » est le défaut du moteur : pas d'entrée.
export function setMode(kid, resourceId, mode) {
  if (mode === "schedule") delete kid.resource_modes[resourceId];
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
  else kid.profiles[day] = clone(kid.profiles.weekend ?? BLOCKED_DAY());
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

// Plages de la frise pour le dessin : position, type et horaires écrits ; `index` renvoie au
// segment d'origine (les heures invalides sont ignorées, comme dans `profileGeometry`).
export function timelineBlocks(segments) {
  const valid = (segments ?? [])
    .map((s, index) => ({ index, start: toMinutes(s.start), type: s.type }))
    .filter((s) => s.start !== null);
  return valid.map((s, i) => {
    const end = i + 1 < valid.length ? valid[i + 1].start : 24 * 60;
    return {
      index: s.index, left: (s.start / 1440) * 100, width: (Math.max(0, end - s.start) / 1440) * 100, type: s.type,
      start: toHHMM(s.start), end: end === 24 * 60 ? "24:00" : toHHMM(end),
    };
  });
}

// Pas des poignées de la frise.
export const SNAP_MINUTES = 5;
const snapDown = (m) => Math.floor(m / SNAP_MINUTES) * SNAP_MINUTES;
const snapUp = (m) => Math.ceil(m / SNAP_MINUTES) * SNAP_MINUTES;

// Position sur la frise (0 = minuit, 1 = minuit suivant) -> minutes, au pas de 5 min.
export function fractionToMinutes(fraction) {
  const f = Number.isFinite(fraction) ? Math.min(1, Math.max(0, fraction)) : 0;
  return Math.round((f * 1440) / SNAP_MINUTES) * SNAP_MINUTES;
}

// Bornes (minutes, sur la grille de 5 min) de la limite qui ouvre le segment `index` : strictement
// après la précédente, strictement avant la suivante (ou 23:55). Null pour 00:00 (fixe), un index
// hors frise, une voisine illisible ou faute de place sur la grille.
export function segmentBounds(segments, index) {
  if (!(index > 0 && index < (segments?.length ?? 0))) return null;
  const prev = toMinutes(segments[index - 1].start);
  const next = index + 1 < segments.length ? toMinutes(segments[index + 1].start) : 24 * 60;
  if (prev === null || next === null) return null;
  const min = snapUp(prev + 1);
  const max = snapDown(next - 1);
  return min <= max ? { min, max } : null;
}

// Déplace la limite du segment `index` vers `minutes` (arrondi à 5 min, borné par les voisines) ;
// renvoie la nouvelle heure, ou null si cette limite ne bouge pas.
export function setSegmentStart(segments, index, minutes) {
  const bounds = segmentBounds(segments, index);
  if (!bounds) return null;
  const snapped = Math.round(minutes / SNAP_MINUTES) * SNAP_MINUTES;
  const value = toHHMM(Math.min(bounds.max, Math.max(bounds.min, snapped)));
  segments[index].start = value;
  return value;
}

// Listes de services du parent : commune (config) et exceptions par enfant.
export const SERVICE_LISTS = {
  leisure: { common: "default_leisure", add: "leisure_add", remove: "leisure_remove" },
  on_demand: { common: "default_on_demand", add: "on_demand_add", remove: "on_demand_remove" },
};
const otherList = (list) => (list === "leisure" ? "on_demand" : "leisure");
// Une config ou un enfant d'avant « sur demande » n'a pas ces clés : listes vides créées au besoin.
const listOf = (obj, key) => {
  if (!Array.isArray(obj[key])) obj[key] = [];
  return obj[key];
};
// Identifiant tel quel (vient d'un menu de vrais ids) : le réécrire le rendrait inconnu du moteur.
const serviceName = (value) => String(value ?? "").trim() || null;

// Pastilles d'une liste pour un enfant : services communs (barrés s'il en est retiré), puis les siens.
export function serviceChips(cfg, kid, list) {
  const keys = SERVICE_LISTS[list];
  const removed = new Set(kid[keys.remove] ?? []);
  const common = cfg[keys.common] ?? [];
  return [
    ...common.map((service) => ({ service, common: true, removed: removed.has(service) })),
    ...(kid[keys.add] ?? []).filter((s) => !common.includes(s)).map((service) => ({ service, common: false, removed: false })),
  ];
}

// Toucher une pastille : un service commun est retiré (ou rétabli) pour l'enfant, un ajout propre disparaît.
export function toggleKidService(cfg, kid, list, service) {
  const keys = SERVICE_LISTS[list];
  if ((cfg[keys.common] ?? []).includes(service)) toggleListValue(listOf(kid, keys.remove), service);
  else {
    const add = listOf(kid, keys.add);
    if (add.includes(service)) add.splice(add.indexOf(service), 1);
  }
}

// Ajout pour un enfant : un service commun retiré est rétabli, sinon ajout propre (sans doublon).
// Renvoie l'identifiant retenu, ou null s'il est vide.
export function addKidService(cfg, kid, list, value) {
  const service = serviceName(value);
  if (!service) return null;
  const keys = SERVICE_LISTS[list];
  if ((cfg[keys.common] ?? []).includes(service)) {
    const remove = listOf(kid, keys.remove);
    if (remove.includes(service)) remove.splice(remove.indexOf(service), 1);
  } else {
    const add = listOf(kid, keys.add);
    if (!add.includes(service)) add.push(service);
  }
  return service;
}

const dropValue = (list, value) => {
  if (list.includes(value)) list.splice(list.indexOf(value), 1);
};

// Ajout à une liste commune ; un service n'est que dans une des deux : s'il est dans l'autre, il
// passe de l'une à l'autre avec les exemptions des enfants (moveCommonService).
export function addCommonService(cfg, list, value) {
  const service = serviceName(value);
  if (!service) return null;
  if ((cfg[SERVICE_LISTS[otherList(list)].common] ?? []).includes(service)) moveCommonService(cfg, service);
  else {
    const target = listOf(cfg, SERVICE_LISTS[list].common);
    if (!target.includes(service)) target.push(service);
  }
  return service;
}

// Retire un service commun ; les exemptions des enfants pour ce service n'ont plus d'objet (et
// exempteraient en silence s'il revenait dans la liste) : retirées aussi.
export function removeCommonService(cfg, list, service) {
  dropValue(listOf(cfg, SERVICE_LISTS[list].common), service);
  for (const kid of cfg.kids ?? []) {
    if (Array.isArray(kid[SERVICE_LISTS[list].remove])) dropValue(kid[SERVICE_LISTS[list].remove], service);
  }
}

// Passe un service commun dans l'autre liste ; un enfant qui en était exempté le reste, et ses
// ajouts devenus redondants disparaissent. Renvoie la liste d'arrivée (null si service inconnu).
export function moveCommonService(cfg, service) {
  const from = ["leisure", "on_demand"].find((l) => (cfg[SERVICE_LISTS[l].common] ?? []).includes(service));
  if (!from) return null;
  const to = otherList(from);
  dropValue(listOf(cfg, SERVICE_LISTS[from].common), service);
  const target = listOf(cfg, SERVICE_LISTS[to].common);
  if (!target.includes(service)) target.push(service);
  for (const kid of cfg.kids ?? []) {
    const oldRemove = listOf(kid, SERVICE_LISTS[from].remove);
    if (oldRemove.includes(service)) {
      oldRemove.splice(oldRemove.indexOf(service), 1);
      const newRemove = listOf(kid, SERVICE_LISTS[to].remove);
      if (!newRemove.includes(service)) newRemove.push(service);
    }
    const add = listOf(kid, SERVICE_LISTS[to].add);
    if (add.includes(service)) add.splice(add.indexOf(service), 1);
  }
  return to;
}

// Nom lisible d'un service d'après un catalogue (id → nom : AdGuard, ou services du parent) ; `known` faux s'il n'y est pas
// (ancienne saisie, faute de frappe) alors que le catalogue est connu.
export function serviceLabel(catalog, service) {
  const name = catalog?.[service];
  return { name: name ?? service, known: !!name || !Object.keys(catalog ?? {}).length };
}

// Choix d'un menu d'ajout : entrées du catalogue (id → nom) pas encore prises, triées par nom.
export function serviceOptions(catalog, taken) {
  const skip = new Set(taken);
  return Object.entries(catalog ?? {})
    .filter(([id]) => !skip.has(id))
    .map(([value, label]) => ({ value, label }))
    .sort((a, b) => a.label.localeCompare(b.label, "fr", { sensitivity: "base" }));
}

// --- Services du parent : chacun regroupe des services AdGuard et des labels d'interrupteurs. Un
// label est rattaché à au plus un service, et jamais à la fois service et cible.

// État d'un interrupteur piloté dans le récapitulatif (texte brut, à échapper) : son état HA puis
// l'état voulu ; `blocked` nul : service ni en loisir ni sur demande d'une cible (laissé tel quel).
export function labelSwitchStatus(sw, hass) {
  const state = sw.blocked === true ? "blocked" : sw.blocked === false ? "allowed" : "unmanaged";
  const wanted = t(hass, `panel.switch_state.${state}`);
  return sw.state ? `${sw.state} · ${wanted}` : wanted;
}

// Labels de cible déjà pris dans le brouillon (enfants et appareils), hors `except`.
function targetLabels(cfg, except = null) {
  return [...(cfg.kids ?? []), ...(cfg.resources ?? [])]
    .filter((e) => e !== except).map((e) => e.target_label).filter(Boolean);
}

// Labels rattachés aux services du brouillon, hors ceux du service `exceptId`.
function serviceLabels(cfg, exceptId = null) {
  return (cfg.services ?? []).filter((s) => s.id !== exceptId).flatMap((s) => (s.labels ?? []).map((l) => l.label_id));
}

const findService = (cfg, id) => (cfg.services ?? []).find((s) => s.id === id);

// Identifiant d'un nouveau service : nom en minuscules sans accents, `_` entre les mots, suffixe
// `_2`, `_3`… s'il est déjà pris.
export function serviceId(name, taken) {
  return uniqueId(slugify(name) || "service", taken ?? []);
}

// Nouveau service sans rattachement ; renvoie son identifiant.
export function addService(cfg, name) {
  const services = (cfg.services ??= []);
  const id = serviceId(name, services.map((s) => s.id));
  services.push({ id, name: String(name ?? "").trim() || id, adguard: [], labels: [] });
  return id;
}

// Retire le service et toutes ses mentions (listes communes, ajouts et retraits des enfants) : le
// moteur refuserait une configuration qui cite un service inconnu.
export function removeService(cfg, id) {
  const i = (cfg.services ?? []).findIndex((s) => s.id === id);
  if (i >= 0) cfg.services.splice(i, 1);
  for (const keys of Object.values(SERVICE_LISTS)) {
    if (Array.isArray(cfg[keys.common])) dropValue(cfg[keys.common], id);
    for (const kid of cfg.kids ?? []) {
      for (const key of [keys.add, keys.remove]) if (Array.isArray(kid[key])) dropValue(kid[key], id);
    }
  }
}

// Nouveau nom (l'identifiant ne change pas) ; faux, sans rien changer, pour un nom vide.
export function renameService(cfg, id, name) {
  const service = findService(cfg, id);
  const value = String(name ?? "").trim();
  if (!service || !value) return false;
  service.name = value;
  return true;
}

// Icône (« mdi:… ») ; vide : la clé disparaît.
export function setServiceIcon(cfg, id, icon) {
  const service = findService(cfg, id);
  if (!service) return;
  if (icon) service.icon = icon;
  else delete service.icon;
}

export function toggleServiceAdguard(cfg, id, adguardId) {
  const service = findService(cfg, id);
  if (service && adguardId) toggleListValue(listOf(service, "adguard"), adguardId);
}

// Rattache (allumé = bloqué par défaut) ou détache un label ; faux, sans rien changer, si le label
// est déjà rattaché à un autre service ou sert de cible.
export function toggleServiceLabel(cfg, id, labelId) {
  const service = findService(cfg, id);
  if (!service || !labelId) return false;
  const labels = listOf(service, "labels");
  const i = labels.findIndex((l) => l.label_id === labelId);
  if (i >= 0) {
    labels.splice(i, 1);
    return true;
  }
  if (serviceLabels(cfg, id).includes(labelId) || targetLabels(cfg).includes(labelId)) return false;
  labels.push({ label_id: labelId, on_means_allowed: false });
  return true;
}

export function setServiceLabelInverted(cfg, id, labelId, on) {
  const link = (findService(cfg, id)?.labels ?? []).find((l) => l.label_id === labelId);
  if (link) link.on_means_allowed = !!on;
}

// Labels HA proposables pour le service `id` : ni rattachés à un autre service, ni de cible.
export function freeLabels(cfg, labels, id) {
  const taken = new Set([...serviceLabels(cfg, id), ...targetLabels(cfg)]);
  return (labels ?? []).filter((l) => !taken.has(l.label_id));
}

// Noms des services du parent (id → nom) : seuls services nommés dans le panneau.
export function serviceNames(cfg) {
  return Object.fromEntries((cfg?.services ?? []).map((s) => [s.id, s.name]));
}

// Interrupteurs pilotés (`label_switches/list`, configuration enregistrée) du service `id`, sans
// doublon ; avec `labelId`, ceux qui portent ce label d'après le registre des entités (`hass.entities`),
// ou tous ceux du service si le registre ne donne pas les labels.
export function serviceSwitches(data, entities, id, labelId = null) {
  const seen = new Set();
  return (data?.switches ?? []).filter((sw) => {
    if (sw.service !== id || seen.has(sw.entity_id)) return false;
    const labels = entities?.[sw.entity_id]?.labels;
    if (labelId && Array.isArray(labels) && !labels.includes(labelId)) return false;
    seen.add(sw.entity_id);
    return true;
  });
}

// Label de cible d'un enfant ou d'un appareil (`null` : aucun) ; faux, sans rien changer, pour un
// label rattaché à un service ou déjà pris par un autre.
export function setTargetLabel(entity, labelId, cfg) {
  if (labelId) {
    if (serviceLabels(cfg).includes(labelId)) return false;
    if (targetLabels(cfg, entity).includes(labelId)) return false;
  }
  // Sans cible, la clé disparaît (comme dans la configuration du serveur) : le brouillon redevient propre.
  if (labelId) entity.target_label = labelId;
  else delete entity.target_label;
  return true;
}

// Nom lisible d'un service de notification : l'appareil de l'application Home Assistant dont il
// porte le nom (`notify.mobile_app_<nom en slug>`), sinon le service lui-même.
export function notifyLabel(service, devices) {
  const slug = String(service ?? "").replace(/^notify\.mobile_app_/, "");
  if (slug === service) return service;
  const dev = (devices ?? []).find((d) => (d.identifiers ?? []).some(([dom]) => dom === "mobile_app")
    && slugify(d.name) === slug);
  return dev ? dev.name_by_user || dev.name : service;
}

// Choix d'un menu de notification : services `notify.*` pas encore pris, triés par libellé ;
// `mobileOnly` ne garde que les téléphones de l'application (seuls à pouvoir répondre aux demandes).
export function notifyOptions(services, devices, taken, mobileOnly = false) {
  const skip = new Set(taken);
  return (services ?? [])
    .filter((s) => !mobileOnly || s.startsWith("mobile_app_"))
    .map((s) => `notify.${s}`)
    .filter((value) => !skip.has(value))
    .map((value) => ({ value, label: notifyLabel(value, devices) }))
    .sort((a, b) => a.label.localeCompare(b.label, "fr", { sensitivity: "base" }));
}

// Services déjà présents dans les deux listes communes (un service n'est que dans l'une des deux).
export function commonServices(cfg) {
  return Object.values(SERVICE_LISTS).flatMap((keys) => cfg[keys.common] ?? []);
}

// « École · Fin de semaine » : journées ayant un profil propre.
export function dayLabels(kid, hass) {
  const days = dayTypes(hass).filter((d) => kid?.profiles && d.value in kid.profiles).map((d) => d.short);
  return days.length ? days.join(" · ") : t(hass, "panel.summary.no_day");
}

// Sous-titre d'un appareil dans la liste : « 2 appareils · 5 intégrations ».
export function resourceSummary(resource, hass) {
  if (!hasDevices(resource)) return t(hass, "panel.summary.legacy");
  const used = kindsOf(resource);
  if (used.includes("nintendo")) return t(hass, "panel.summary.nintendo");
  if (!used.length) return t(hass, "panel.summary.no_integration");
  const count = plural(hass, "panel.summary.integrations", used.length);
  return resource.devices.length > 1 ? `${plural(hass, "panel.summary.devices", resource.devices.length)} · ${count}` : count;
}

const ENTITY_KINDS = ["media_player", "switch"];
const DEVICE_DETAILS = { adguard_services: "AdGuard Home", nintendo: "Nintendo" };

// Ligne d'une intégration : ce qui est choisi (`title`, null tant que rien ne l'est), le détail
// (intégration HA · entité · options) et si l'entité ou l'appareil existe dans HA.
export function integrationSummary(hass, registry, integ) {
  if (ENTITY_KINDS.includes(integ.kind)) {
    const id = integ.entity_id || "";
    const state = id ? hass?.states?.[id] : null;
    const entry = id ? hass?.entities?.[id] : null;
    const platform = platformLabel(hass, entry?.platform);
    const detail = [platform, id || null, integ.kind === "switch" && integ.turn_on_when_allowed ? t(hass, "panel.summary.turned_on_when_allowed") : null]
      .filter(Boolean).join(" · ");
    return { title: id ? state?.attributes?.friendly_name || id : null, detail, found: !!state };
  }
  const id = integ.device_id || "";
  const device = id ? (registry ?? []).find((d) => d.id === id) : null;
  return {
    title: id ? device?.name_by_user || device?.name || id : null,
    detail: DEVICE_DETAILS[integ.kind] ?? integ.kind,
    found: !!device,
  };
}

// Couleur d'un enfant utilisable dans un style : #rrggbb seulement.
export function safeColor(value) {
  return typeof value === "string" && /^#[0-9a-f]{6}$/i.test(value) ? value : null;
}

// Nom d'icône Home Assistant (« mdi:television ») : tout autre texte n'est pas enregistré.
export function isIconName(value) {
  return typeof value === "string" && /^[a-z0-9-]+:[a-z0-9-]+$/.test(value);
}

export function isDirty(original, draft) {
  return JSON.stringify(original) !== JSON.stringify(draft);
}

// Statut d'un téléphone de demandes (`config/get` → `phones`) : pastille du panneau.
const PHONE_STATUSES = ["ok", "unbound", "missing", "changed", "ambiguous"];

export function phoneBadge(status, hass) {
  if (!PHONE_STATUSES.includes(status)) return { label: String(status ?? ""), tone: "warn" };
  return { label: t(hass, `panel.phone.${status}`), tone: status === "ok" ? "ok" : "warn" };
}

// « Réassocier » d'un téléphone de demandes : proposé seulement pour `unbound` et `changed` (pour
// `missing` et `ambiguous`, le serveur refuserait). `current` : propriétaire actuel de l'appareil,
// celui qui deviendra parent (à montrer, il diffère du mémorisé) ; `null` s'il est inconnu.
export function phoneRebind(phone, hass) {
  if (phone?.status !== "unbound" && phone?.status !== "changed") return null;
  const current = phone.current_name ?? null;
  return { current, label: current ? t(hass, "panel.phone.rebind_to", { name: current }) : t(hass, "panel.phone.rebind") };
}

// Vrai si l'utilisateur, non administrateur, n'aura plus aucun téléphone `ok` à son nom dans les
// destinataires des demandes une fois le brouillon enregistré : il ne sera plus parent.
export function losesParentOnSave(draft, phones, userId, isAdmin) {
  if (isAdmin) return false;
  return !(draft?.request_notify ?? []).some((t) => phones?.[t]?.status === "ok" && phones[t].owner === userId);
}

// Message `config/set` : `rebind` (téléphones à réassocier) voyage à côté de la configuration,
// jamais dedans ; seuls les téléphones encore listés sont réassociés. `request_notify_owners`
// n'est pas envoyé : le serveur détermine les propriétaires (et ignore toute valeur reçue).
export function saveMessage(draft) {
  const { rebind = [], request_notify_owners: _owners, ...config } = draft;
  const listed = new Set(config.request_notify ?? []);
  return { type: "parental_control/config/set", config, rebind: rebind.filter((t) => listed.has(t)) };
}
