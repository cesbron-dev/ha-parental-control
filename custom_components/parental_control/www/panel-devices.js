// Onglet « Appareils » du panneau Règles : méthodes ajoutées au panneau (`this` = le panneau).
import { esc } from "./lib.js";
import * as L from "./panel-lib.js";
import { opt, pick } from "./panel-style.js";

const NINTENDO_DOMAIN = "nintendo_parental_controls";
const ADGUARD_DOMAIN = "adguard_clients";
// Icône déduite comme sur la carte appareil (Nintendo, sinon lecteur, sinon interrupteur, sinon AdGuard).
const KIND_ICONS = { nintendo: "mdi:nintendo-switch", media_player: "mdi:television", switch: "mdi:power-socket-eu", adguard_services: "mdi:cellphone" };
const INTEGRATION_ICONS = { media_player: "mdi:play-box-outline", switch: "mdi:power-socket-eu", adguard_services: "mdi:shield-half-full", nintendo: "mdi:nintendo-switch" };

export const devicesView = {
  _resIcon(res) {
    const kinds = L.hasDevices(res) ? res.devices.flatMap((dev) => dev.integrations.map((i) => i.kind)) : [res.kind];
    const kind = ["nintendo", "media_player", "switch", "adguard_services"].find((k) => kinds.includes(k));
    return pick(KIND_ICONS, kind, "mdi:shield-account");
  },

  _resItem(i) {
    const r = this._draft.resources[i];
    return `<button type="button" class="it ${i === this._res ? "on" : ""}" data-act="res" data-arg="${i}" data-item="resources.${i}">
      <div class="av"><ha-icon icon="${esc(r.icon || this._resIcon(r))}"></ha-icon></div>
      <div><div class="n">${esc(r.name ?? r.id)}</div><div class="s">${esc(L.resourceSummary(r, this._hass))}</div></div></button>`;
  },

  _resources() {
    const d = this._draft;
    const res = d.resources[this._res];
    const adding = this._adding === "res"
      ? `<div class="adding"><input data-input="new-res" data-enter="add-res" placeholder="${esc(this._t("panel.devices.name_placeholder"))}" autofocus>
          <select data-input="new-res-kind" title="${esc(this._t("panel.devices.first_integration"))}">${L.kinds(this._hass).map((k) => opt(k.value, k.label, "adguard_services")).join("")}</select>
          <div class="row">${this._btn("add-res", this._t("panel.action.add"), { cls: "btn primary" })}${this._btn("adding", this._t("panel.action.cancel"), { cls: "btn" })}</div></div>`
      : this._btn("adding", this._t("panel.devices.add"), { arg: "res", cls: "link" });
    const list = `<div class="list">${d.resources.map((_, i) => this._resItem(i)).join("")}${adding}</div>`;
    if (!res) return `<div class="cols"><div class="side">${list}</div><div class="card mut">${esc(this._t("panel.devices.empty"))}</div></div>`;
    const p = `resources.${this._res}`;
    return `<div class="cols"><div class="side">${list}</div><div>
      ${this._resHead(res, p)}
      ${this._tree(res, p)}
    </div></div>`;
  },

  // Carte d'en-tête : icône, nom, menu ⋮ (identifiant, icône, suppression), enfants et quotas.
  _resHead(res, p) {
    const d = this._draft;
    const owners = res.owners ?? [];
    const kids = d.kids.length
      ? d.kids.map((k) => `<button type="button" class="${owners.includes(k.id) ? "" : "off"}" data-act="toggle-owner" data-arg="${esc(k.id)}"
          title="${esc(this._t(owners.includes(k.id) ? "panel.devices.owner_on" : "panel.devices.owner_off"))}">${k.emoji ? `${esc(k.emoji)} ` : ""}${esc(k.name)}</button>`).join("")
      : `<span class="mut">${esc(this._t("panel.devices.no_kid"))}</span>`;
    const quotas = L.dayTypes(this._hass).map((day) => `<label class="field"><span>${esc(day.short)}</span>
      <input type="number" min="0" data-type="int" data-path="${p}.quota_minutes.${day.value}" value="${esc(res.quota_minutes?.[day.value] ?? "")}" placeholder="—" title="${esc(this._t("panel.devices.quota_title"))}"></label>`).join("");
    const target = this._targetLabelField(res, p, { spaced: false });
    const editable = this._newIds.has(`res:${res.id}`);
    const menu = this._menu === "res" ? `<div class="menu">
        <label class="field"><span>${esc(this._t(editable ? "panel.devices.id_editable" : "panel.devices.id_frozen"))}</span>
          <input value="${esc(res.id)}" ${editable ? `data-rename="res:${esc(res.id)}"` : "readonly"}></label>
        <label class="field"><span>${esc(this._t("panel.devices.icon"))}</span><span class="icon-field">
          <input data-path="${p}.icon" value="${esc(res.icon ?? "")}" placeholder="${esc(this._resIcon(res))}" title="${esc(this._t("panel.devices.icon_title"))}">
          <span class="preview"><ha-icon icon="${esc(res.icon || this._resIcon(res))}" data-icon-of="${p}"></ha-icon></span></span></label>
        ${this._btn("del-res", this._t("panel.devices.delete"), { cls: "link danger", icon: "mdi:delete-outline", confirmKey: `del-res:${res.id}` })}
      </div>` : "";
    return `<div class="card res-head">
      <h2><span class="big"><ha-icon icon="${esc(res.icon || this._resIcon(res))}" data-icon-of="${p}"></ha-icon></span>
        <input class="title-in" data-path="${p}.name" value="${esc(res.name ?? "")}" title="${esc(this._t("panel.devices.name_title"))}">
        <span class="menu-wrap">${this._btn("menu", "", { arg: "res", icon: "mdi:dots-vertical", cls: "icon-btn", title: this._t("panel.devices.menu_title") })}${menu}</span></h2>
      <div class="res-cfg">
        <div><div class="mut label">${esc(this._t("panel.devices.kids"))}</div><div class="kd">${kids}</div></div>
        ${target && `<div>${target}</div>`}
        <div class="q-wrap"><div class="mut label">${esc(this._t("panel.devices.quota"))}</div><div class="q">${quotas}</div></div>
      </div>
    </div>`;
  },

  // « Ce qui est piloté » : un groupe par appareil physique, une ligne par intégration.
  _tree(res, p) {
    if (!L.hasDevices(res)) {
      return `<div class="card"><h2>${esc(this._t("panel.devices.tree"))}</h2><div class="mut">${esc(this._t("panel.devices.legacy"))}</div></div>`;
    }
    const allowed = L.integrationKindsAllowed(res);
    const groups = res.devices.map((dev, j) => this._physical(res, dev, j, `${p}.devices.${j}`, allowed)).join("");
    const addDev = !allowed.length ? ""
      : this._adding === "dev"
        ? `<div class="adding tree-foot"><div class="row"><input data-input="new-dev" data-enter="add-dev" placeholder="${esc(this._t("panel.devices.physical_placeholder"))}" autofocus style="flex:1 1 220px">
            ${this._btn("add-dev", this._t("panel.action.add"), { cls: "btn primary" })}${this._btn("adding", this._t("panel.action.cancel"), { cls: "btn" })}</div></div>`
        : "";
    const addLink = allowed.length && this._adding !== "dev" ? this._btn("adding", this._t("panel.devices.add_physical"), { arg: "dev", cls: "link" }) : "";
    return `<div class="card"><h2>${esc(this._t("panel.devices.tree"))}<span class="sp"></span>${addLink}</h2>${groups}${addDev}</div>`;
  },

  _physical(res, dev, j, p, allowed) {
    const targets = L.moveTargets(this._draft, this._res, j);
    const move = targets.length ? `<select class="link-select" data-move="${j}" title="${esc(this._t("panel.devices.move_title"))}">
        <option value="" selected>${esc(this._t("panel.devices.move"))}</option>
        ${targets.map((i) => opt(String(i), this._draft.resources[i].name, null)).join("")}
      </select><span class="sep">·</span>` : "";
    const rows = dev.integrations.map((integ, k) => this._integration(res, integ, j, k, `${p}.integrations.${k}`)).join("");
    const add = allowed.length ? `<div class="addrow"><select data-add-integ="${j}" title="${esc(this._t("panel.devices.add_integration_title"))}">
        <option value="" selected>${esc(this._t("panel.devices.add_integration"))}</option>
        ${allowed.map((kind) => opt(kind, this._t(`panel.kind.${kind}`), null)).join("")}
      </select></div>` : "";
    return `<div class="grp">
      <div class="gh"><ha-icon icon="mdi:monitor-cellphone"></ha-icon>
        <input data-path="${p}.name" value="${esc(dev.name ?? "")}" title="${esc(this._t("panel.devices.physical_title"))}">
        <span class="mut">${esc(this._t("panel.devices.physical"))}</span><span class="sp"></span>
        ${move}${this._btn("del-dev", this._t("panel.action.delete"), { arg: j, cls: "quiet danger", title: this._t("panel.devices.delete_physical"), confirmKey: `del-dev:${res.id}:${j}` })}
      </div>
      ${rows || `<div class="addrow mut">${esc(this._t("panel.devices.no_integration"))}</div>`}
      ${add}
    </div>`;
  },

  // Une ligne par intégration ; un clic l'ouvre pour l'éditer (choix et options sous la ligne).
  _integration(res, integ, j, k, p) {
    const key = `${j}:${k}`;
    const open = this._edit === key;
    const s = L.integrationSummary(this._hass, this._devices, integ);
    const kind = L.kinds(this._hass).find((x) => x.value === integ.kind)?.short ?? integ.kind;
    const what = s.title
      ? `<span class="ent">${esc(s.title)}${s.detail ? `<small>${esc(s.detail)}</small>` : ""}</span>`
      : `<span class="ent none">${esc(this._t("panel.devices.to_choose"))}${s.detail ? `<small>${esc(s.detail)}</small>` : ""}</span>`;
    const edit = open ? `<div class="edit">${this._kindOptions(integ, p, `${j}-${k}`)}
        <div class="row">${this._btn("edit-integ", this._t("panel.action.close"), { arg: key, cls: "btn" })}
          ${this._btn("del-integ", this._t("panel.devices.remove_integration"), { arg: key, cls: "quiet danger", icon: "mdi:delete-outline", confirmKey: `del-integ:${res.id}:${key}` })}</div>
      </div>` : "";
    return `<div class="ir ${open ? "open" : ""}" data-act="edit-integ" data-arg="${key}" title="${esc(this._t(open ? "panel.action.close" : "panel.action.edit"))}">
        <ha-icon icon="${pick(INTEGRATION_ICONS, integ.kind, "mdi:puzzle")}"></ha-icon>
        <span class="ty">${esc(kind)}</span>${what}${this._dot(s.found, p)}
        <button type="button" class="icon-btn" data-act="edit-integ" data-arg="${key}" title="${esc(this._t("panel.action.edit"))}"><ha-icon icon="mdi:dots-vertical"></ha-icon></button>
      </div>${edit}`;
  },

  // Pastille : l'entité (lecteur, interrupteur) ou l'appareil (AdGuard, Nintendo) existe-t-il dans HA ?
  _dot(found, p) {
    return `<span class="st ${found ? "found" : "missing"}" data-dot="${p}"><span class="dot"></span>${esc(this._t(found ? "panel.devices.found" : "panel.devices.missing"))}</span>`;
  },

  _deviceSelect(path, domain, current) {
    const devices = this._devicesOf(domain);
    const known = devices.some((dev) => dev.id === current);
    return `<select data-path="${path}">
      <option value="" ${current ? "" : "selected"}>${esc(this._t("panel.action.choose"))}</option>
      ${!known && current ? opt(current, this._t("panel.not_found_value", { value: current }), current) : ""}
      ${devices.map((dev) => opt(dev.id, dev.name, current)).join("")}
    </select>`;
  },

  // Liste des entités d'un domaine (nom de l'appareil — intégration) ; garde l'entité actuelle
  // même si elle a disparu, pour la voir et la changer.
  _entitySelect(path, domain, current) {
    const choices = L.entityChoices(this._hass, domain);
    const known = choices.some((c) => c.value === current);
    return `<select data-path="${path}">
      <option value="" ${current ? "" : "selected"}>${esc(this._t("panel.action.choose"))}</option>
      ${!known && current ? opt(current, this._t("panel.not_found_value", { value: current }), current) : ""}
      ${choices.map((c) => opt(c.value, c.label, current)).join("")}
    </select>`;
  },

  _kindOptions(integ, p, key) {
    if (integ.kind === "media_player") {
      return `<label class="field"><span>${esc(this._t("panel.devices.player"))}</span>${this._entitySelect(`${p}.entity_id`, "media_player", integ.entity_id)}</label>`;
    }
    if (integ.kind === "switch") {
      return `<label class="field"><span>${esc(this._t("panel.devices.switch"))}</span>${this._entitySelect(`${p}.entity_id`, "switch", integ.entity_id)}</label>
        <label class="check"><input type="checkbox" data-type="bool" data-path="${p}.turn_on_when_allowed" ${integ.turn_on_when_allowed ? "checked" : ""}>
          ${esc(this._t("panel.devices.turn_on"))}</label>`;
    }
    if (integ.kind === "adguard_services") {
      return `<label class="field"><span>${esc(this._t("panel.devices.adguard"))}</span>${this._deviceSelect(`${p}.device_id`, ADGUARD_DOMAIN, integ.device_id)}</label>`;
    }
    const ents = this._entities("", integ.device_id || null);
    return `<div class="grid">
      <label class="field"><span>${esc(this._t("panel.devices.nintendo"))}</span>${this._deviceSelect(`${p}.device_id`, NINTENDO_DOMAIN, integ.device_id)}</label>
      <label class="field"><span>${esc(this._t("panel.devices.limit"))}</span><input data-path="${p}.limit_entity" value="${esc(integ.limit_entity ?? "")}" list="nent-${key}" placeholder="number.…"></label>
      <label class="field"><span>${esc(this._t("panel.devices.remaining"))}</span><input data-path="${p}.remaining_entity" value="${esc(integ.remaining_entity ?? "")}" list="nent-${key}" placeholder="sensor.…"></label>
      <label class="field"><span>${esc(this._t("panel.devices.used"))}</span><input data-path="${p}.used_entity" value="${esc(integ.used_entity ?? "")}" list="nent-${key}" placeholder="sensor.…"></label>
    </div>${this._datalist(`nent-${key}`, ents)}`;
  },
};
