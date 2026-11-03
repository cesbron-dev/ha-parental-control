// Logique pure du panneau « Règles » : édition en place du brouillon de configuration (même forme
// que `parental_control/config/get`), sans DOM. Le moteur reste seul juge de la validité (config/set).

export const DAY_TYPES = [
  { value: "ecole", label: "École", short: "École", required: true },
  { value: "fin_de_semaine", label: "Fin de semaine", short: "Fin de semaine", required: true },
  { value: "conge_peda", label: "Congé pédagogique", short: "Congé péd.", required: false },
  { value: "vacances", label: "Vacances", short: "Vacances", required: false },
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
  return { version: 2, default_leisure: [], default_on_demand: [], calendar_map: {}, notify: [], kids: [], resources: [] };
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

// Une ressource v1 (collée dans l'onglet JSON) n'a pas d'appareils : son seul type est `kind`.
const kindsOf = (resource) => (hasDevices(resource)
  ? resource.devices.flatMap((d) => d.integrations?.map((i) => i.kind) ?? [])
  : resource?.kind ? [resource.kind] : []);

// Types ajoutables à la ressource : une Nintendo doit rester seule dans sa ressource ; rien dans une
// ressource v1 (le moteur la convertit à l'enregistrement).
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

// Listes de services AdGuard : commune (config) et exceptions par enfant.
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
const serviceName = (value) => String(value ?? "").trim().toLowerCase() || null;

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
// Renvoie le nom retenu (minuscules), ou null s'il est vide.
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

// Nom lisible d'un service d'après le catalogue AdGuard (id → nom) ; `known` faux s'il n'y est pas
// (ancienne saisie, faute de frappe) alors que le catalogue est connu.
export function serviceLabel(catalog, service) {
  const name = catalog?.[service];
  return { name: name ?? service, known: !!name || !Object.keys(catalog ?? {}).length };
}

// Choix du menu « + Ajouter » : services du catalogue pas encore pris, triés par nom.
export function serviceOptions(catalog, taken) {
  const skip = new Set(taken);
  return Object.entries(catalog ?? {})
    .filter(([id]) => !skip.has(id))
    .map(([value, label]) => ({ value, label }))
    .sort((a, b) => a.label.localeCompare(b.label, "fr", { sensitivity: "base" }));
}

// Services déjà présents dans les deux listes communes (un service n'est que dans l'une des deux).
export function commonServices(cfg) {
  return Object.values(SERVICE_LISTS).flatMap((keys) => cfg[keys.common] ?? []);
}

// « École · Fin de semaine » : journées ayant un profil propre.
export function dayLabels(kid) {
  const days = DAY_TYPES.filter((d) => kid?.profiles && d.value in kid.profiles).map((d) => d.short);
  return days.length ? days.join(" · ") : "Aucune journée";
}

const plural = (n, word) => `${n} ${word}${n > 1 ? "s" : ""}`;

// Sous-titre d'un appareil dans la liste : « 2 appareils · 5 intégrations ».
export function resourceSummary(resource) {
  if (!hasDevices(resource)) return "Format ancien";
  const kinds = kindsOf(resource);
  if (kinds.includes("nintendo")) return "Console Nintendo";
  if (!kinds.length) return "Aucune intégration";
  const count = plural(kinds.length, "intégration");
  return resource.devices.length > 1 ? `${plural(resource.devices.length, "appareil")} · ${count}` : count;
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
    const platform = entry?.platform ? PLATFORM_LABELS[entry.platform] ?? entry.platform : null;
    const detail = [platform, id || null, integ.kind === "switch" && integ.turn_on_when_allowed ? "rallumée à l'autorisation" : null]
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
