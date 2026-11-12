// Onglet « Enfants » du panneau Règles : méthodes ajoutées au panneau (`this` = le panneau).
import { esc } from "./lib.js";
import { formatHour } from "./i18n.js";
import * as L from "./panel-lib.js";
import { SEGMENT_COLORS, KID_COLORS, opt, pick } from "./panel-style.js";

const RULER = [0, 3, 6, 9, 12, 15, 18, 21, 24];
const NARROW = 6; // % de la journée sous lequel une plage n'affiche pas son texte (info-bulle seulement)

export const kidsView = {
  _avatar(kid) {
    const color = L.safeColor(kid.color);
    const face = kid.emoji ? esc(kid.emoji) : esc((kid.name ?? "?").trim().charAt(0).toUpperCase() || "?");
    return `<div class="av" ${color ? `style="background:${color}33"` : ""}>${face}</div>`;
  },

  _kidItem(i) {
    const k = this._draft.kids[i];
    return `<button type="button" class="it ${i === this._kid ? "on" : ""}" data-act="kid" data-arg="${i}" data-item="kids.${i}">
      ${this._avatar(k)}<div><div class="n">${esc(k.name)}</div><div class="s">${esc(L.dayLabels(k, this._hass))}</div></div></button>`;
  },

  _kids() {
    const d = this._draft;
    const kid = d.kids[this._kid];
    const adding = this._adding === "kid"
      ? `<div class="adding"><input data-input="new-kid" data-enter="add-kid" placeholder="${esc(this._t("panel.kids.name_placeholder"))}" autofocus>
          <div class="row">${this._btn("add-kid", this._t("panel.action.add"), { cls: "btn primary" })}${this._btn("adding", this._t("panel.action.cancel"), { cls: "btn" })}</div></div>`
      : this._btn("adding", this._t("panel.kids.add"), { arg: "kid", cls: "link" });
    const list = `<div class="list">${d.kids.map((_, i) => this._kidItem(i)).join("")}${adding}</div>`;
    if (!kid) return `<div class="cols"><div class="side">${list}</div><div class="card mut">${esc(this._t("panel.kids.empty"))}</div></div>`;
    const p = `kids.${this._kid}`;
    return `<div class="cols">
      <div class="side">${list}${this._identity(kid, p)}</div>
      <div>
        ${this._dayCard(kid, p)}
        <div class="duo">${this._servicesCard(kid)}${this._modesCard(kid)}</div>
        <div class="sensitive">${this._btn("del-kid", this._t("panel.kids.delete"), { cls: "quiet danger", icon: "mdi:delete-outline", confirmKey: `del-kid:${kid.id}` })}</div>
      </div>
    </div>`;
  },

  _identity(kid, p) {
    const color = L.safeColor(kid.color);
    const known = KID_COLORS.some((c) => c.value.toLowerCase() === String(kid.color ?? "").toLowerCase());
    const colors = `<option value="" ${kid.color ? "" : "selected"}>${esc(this._t("panel.kids.color_none"))}</option>
      ${kid.color && !known ? opt(kid.color, this._t("panel.kids.color_custom", { color: kid.color }), kid.color) : ""}
      ${KID_COLORS.map((c) => `<option value="${c.value}" ${c.value.toLowerCase() === String(kid.color ?? "").toLowerCase() ? "selected" : ""}>${esc(this._t(`panel.color.${c.name}`))}</option>`).join("")}`;
    const calendars = this._entities("calendar.");
    const cal = kid.calendar ?? "";
    const calOptions = `<option value="" ${cal ? "" : "selected"}>${esc(this._t("panel.kids.calendar_none"))}</option>
      ${cal && !calendars.includes(cal) ? opt(cal, this._t("panel.not_found_value", { value: cal }), cal) : ""}
      ${calendars.map((c) => opt(c, this._hass?.states?.[c]?.attributes?.friendly_name || c, cal)).join("")}`;
    const editable = this._newIds.has(`kid:${kid.id}`);
    const id = editable
      ? `<label class="field"><span>${esc(this._t("panel.kids.id_editable"))}</span><input value="${esc(kid.id)}" data-rename="kid:${esc(kid.id)}"></label>`
      : `<div class="mut" style="margin-top:14px">${esc(this._t("panel.kids.id", { id: kid.id }))}</div>`;
    return `<div class="card"><h2>${esc(this._t("panel.kids.identity"))}</h2>
      <label class="field"><span>${esc(this._t("panel.kids.name"))}</span><input data-path="${p}.name" value="${esc(kid.name)}"></label>
      <div class="pair" style="margin-top:14px">
        <label class="field"><span>${esc(this._t("panel.kids.emoji"))}</span><input data-path="${p}.emoji" value="${esc(kid.emoji ?? "")}" placeholder="🎧"></label>
        <label class="field"><span>${esc(this._t("panel.kids.color"))}</span><span class="with-dot">
          <span class="dot" style="background:${color ?? "transparent"};${color ? "" : "border:1px solid var(--pc-muted)"}"></span>
          <select data-path="${p}.color">${colors}</select></span></label>
      </div>
      <label class="field" style="margin-top:14px"><span>${esc(this._t("panel.kids.calendar"))}</span><select data-path="${p}.calendar">${calOptions}</select></label>
      ${this._targetLabelField(kid, p)}
      ${id}
    </div>`;
  },

  // Carte « Journée type » : sélecteur de journée, quota, frise à poignées et une ligne par plage.
  _dayCard(kid, p) {
    const days = L.dayTypes(this._hass);
    const dayType = days.find((dt) => dt.value === this._day) ?? days[0];
    const day = dayType.value;
    const picker = `<span class="seg">${days.map((dt) => {
      const own = dt.value in kid.profiles;
      const title = own ? "" : this._t("panel.kids.follows_weekend");
      return `<button type="button" class="${dt.value === day ? "on" : ""} ${own ? "" : "dim"}" data-act="day" data-arg="${dt.value}" ${title ? `title="${esc(title)}"` : ""}>${esc(dt.short)}</button>`;
    }).join("")}</span>`;
    const heading = `<h2>${esc(this._t("panel.kids.day"))} <span class="sp"></span>${picker}</h2>`;
    const prof = kid.profiles[day];
    if (!prof) {
      return `<div class="card">${heading}
        <div class="profile-note"><span class="mut">${esc(this._t("panel.kids.day_follows_weekend", { day: dayType.label }))}</span>
          ${this._btn("toggle-profile", this._t("panel.kids.own_profile"), { arg: day, cls: "link" })}</div></div>`;
    }
    const pp = `${p}.profiles.${day}`;
    const rows = prof.segments.map((s, i) => this._segRow(s, i, pp, day)).join("");
    const drop = dayType.required ? "" : this._btn("toggle-profile", this._t("panel.kids.drop_profile"), { arg: day, cls: "quiet danger", confirmKey: `drop-profile:${kid.id}:${day}` });
    return `<div class="card">${heading}
      <div class="row quota-row"><span class="mut">${esc(this._t("panel.kids.quota"))}</span>
        <input type="number" min="0" data-type="int" data-path="${pp}.quota_minutes" value="${esc(prof.quota_minutes ?? "")}" placeholder="${esc(this._t("panel.kids.quota_none"))}" title="${esc(this._t("panel.kids.quota_title"))}">
        <span class="mut">${esc(this._t("panel.unit_min"))}</span><span class="sp"></span><span class="mut">${esc(this._t("panel.kids.drag_hint"))}</span></div>
      <div class="tl" data-tl="${pp}">${this._timeline(prof.segments, pp)}</div>
      <div class="ruler">${RULER.map((h) => `<span style="left:${(h / 24) * 100}%">${esc(formatHour(this._hass, h))}</span>`).join("")}</div>
      <div class="segs">${rows}</div>
      <div class="row" style="margin-top:10px">${this._btn("add-seg", this._t("panel.kids.add_segment"), { arg: day, cls: "link" })}<span class="sp"></span>${drop}</div>
    </div>`;
  },

  // Intérieur de la frise : plages colorées avec type et horaires, poignées blanches aux limites.
  _timeline(segments, pp) {
    const blocks = L.timelineBlocks(segments);
    const types = L.segmentTypes(this._hass);
    const label = (type) => types.find((st) => st.value === type)?.label ?? type;
    const html = blocks.map((b) => `<div class="b" style="left:${b.left}%;width:${b.width}%;background:${pick(SEGMENT_COLORS, b.type, "#666")}"
        title="${esc(label(b.type))} ${b.start} – ${b.end}">${b.width < NARROW ? "" : `<strong>${esc(label(b.type))}</strong><small>${b.start} – ${b.end}</small>`}</div>`).join("");
    const handles = blocks.filter((b) => b.index > 0).map((b) => {
      const bounds = L.segmentBounds(segments, b.index);
      const [hh, mm] = b.start.split(":").map(Number);
      const aria = bounds ? `tabindex="0" role="slider" aria-label="${esc(this._t("panel.kids.segment_start", { index: b.index + 1 }))}" aria-valuemin="${bounds.min}"
        aria-valuemax="${bounds.max}" aria-valuenow="${hh * 60 + mm}" aria-valuetext="${b.start}"` : "";
      return `<span class="h ${bounds ? "" : "fixed"}" style="left:${b.left}%" data-handle="${b.index}" data-pp="${pp}" ${aria}></span>`;
    }).join("");
    return `<div class="blocks">${html}</div>${handles}`;
  },

  _segRow(s, i, pp, day) {
    const color = pick(SEGMENT_COLORS, s.type, "#666");
    const time = i === 0
      ? `<span class="t0">00:00</span>`
      : `<input type="time" step="60" data-path="${pp}.segments.${i}.start" value="${esc(s.start)}">`;
    return `<div class="segrow">
      ${time}
      <span class="chip"><span class="dot" style="background:${color}"></span>
        <select data-path="${pp}.segments.${i}.type" title="${esc(this._t("panel.kids.segment_type"))}">${L.segmentTypes(this._hass).map((st) => opt(st.value, st.label, s.type)).join("")}</select></span>
      <label class="warn">${esc(this._t("panel.kids.warn_before"))} <input type="number" min="0" data-type="int" data-path="${pp}.segments.${i}.warn_minutes" value="${esc(s.warn_minutes ?? "")}" placeholder="5" title="${esc(this._t("panel.kids.warn_title"))}"> ${esc(this._t("panel.kids.warn_after"))}</label>
      ${i === 0 ? "<span></span>" : this._btn("del-seg", "", { arg: `${day}:${i}`, icon: "mdi:close", cls: "icon-btn", title: this._t("panel.kids.remove_segment") })}
    </div>`;
  },

  // Carte « Services » : loisirs et services sur demande, pastilles communes puis ajouts de l'enfant.
  _servicesCard(kid) {
    const groups = ["leisure", "on_demand"].map((list) => {
      const title = esc(this._t(`panel.kids.${list}`));
      const sub = esc(this._t(`panel.kids.${list}_sub`));
      return `<div class="group"><h3>${title} <span class="mut">(${sub})</span></h3>
        <div class="lz" data-chips="kid:${list}">${this._kidChips(kid, list)}</div></div>`;
    }).join("");
    return `<div class="card"><h2>${esc(this._t("panel.kids.services"))}</h2>${groups}
      <div class="mut help">${esc(this._t("panel.kids.services_help", { name: kid.name }))}</div></div>`;
  },

  // Pastilles d'une liste pour l'enfant, puis le champ « + Ajouter » (redessinées sur place après un ajout).
  _kidChips(kid, list) {
    const chips = L.serviceChips(this._draft, kid, list).map((c) => {
      const name = this._svcName(c.service);
      const key = !c.common ? "chip_own" : c.removed ? "chip_restore" : "chip_allow";
      const title = this._t(`panel.kids.${key}`, { name: kid.name });
      const mark = c.removed ? "↺" : "✕";
      return `<button type="button" class="pill ${c.removed ? "off" : ""} ${c.common ? "" : "own"} ${this._svcClass(c.service)}" data-act="kid-svc" data-list="${list}" data-arg="${esc(c.service)}" title="${esc(title)}" aria-label="${esc(this._t("panel.kids.chip_aria", { service: name, title }))}">
        ${this._svcIcon(c.service)}${esc(name)}<span class="x" aria-hidden="true">${mark}</span></button>`;
    }).join("");
    const taken = L.serviceChips(this._draft, kid, list).filter((c) => !c.removed).map((c) => c.service);
    return chips + this._serviceAdder(`kid-svc-${list}`, "add-kid-svc", list, taken);
  },

  // Carte « Règle par appareil » : contrôle segmenté par appareil de l'enfant.
  _modesCard(kid) {
    const owned = this._draft.resources.filter((r) => (r.owners ?? []).includes(kid.id));
    const modes = L.modes(this._hass);
    const rows = owned.map((r) => {
      const current = kid.resource_modes[r.id] ?? "schedule";
      return `<div class="mode"><span class="nm"><ha-icon icon="${esc(r.icon || this._resIcon(r))}"></ha-icon><span>${esc(r.name)}</span></span>
        <span class="seg">${modes.map((m) => `<button type="button" class="${m.value === current ? "on" : ""}" data-act="set-mode" data-arg="${m.value}" data-res="${esc(r.id)}" title="${esc(m.label)}">${esc(m.short)}</button>`).join("")}</span></div>`;
    }).join("");
    return `<div class="card"><h2>${esc(this._t("panel.kids.modes"))}</h2>
      ${rows ? `<div class="modes">${rows}</div>` : `<div class="mut">${esc(this._t("panel.kids.modes_empty"))}</div>`}</div>`;
  },
};
