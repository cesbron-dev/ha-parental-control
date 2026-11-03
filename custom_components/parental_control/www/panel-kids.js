// Onglet « Enfants » du panneau Règles : méthodes ajoutées au panneau (`this` = le panneau).
import { esc } from "./lib.js";
import * as L from "./panel-lib.js";
import { SEGMENT_COLORS, KID_COLORS, opt, pick } from "./panel-style.js";

const RULER = [0, 3, 6, 9, 12, 15, 18, 21, 24];
const NARROW = 6; // % de la journée sous lequel une plage n'affiche pas son texte (info-bulle seulement)
const MODE_SHORT = { suit_frise: "Frise", sur_demande: "Sur demande", bloque: "Bloqué", libre: "Libre" };
const LIST_TITLES = {
  leisure: ["Loisirs", "bloqués hors plages libres"],
  on_demand: ["Sur demande", "toujours bloqués sauf autorisation"],
};

export const kidsView = {
  _avatar(kid) {
    const color = L.safeColor(kid.color);
    const face = kid.emoji ? esc(kid.emoji) : esc((kid.name ?? "?").trim().charAt(0).toUpperCase() || "?");
    return `<div class="av" ${color ? `style="background:${color}33"` : ""}>${face}</div>`;
  },

  _kidItem(i) {
    const k = this._draft.kids[i];
    return `<button type="button" class="it ${i === this._kid ? "on" : ""}" data-act="kid" data-arg="${i}" data-item="kids.${i}">
      ${this._avatar(k)}<div><div class="n">${esc(k.name)}</div><div class="s">${esc(L.dayLabels(k))}</div></div></button>`;
  },

  _kids() {
    const d = this._draft;
    const kid = d.kids[this._kid];
    const adding = this._adding === "kid"
      ? `<div class="adding"><input data-input="new-kid" data-enter="add-kid" placeholder="Prénom" autofocus>
          <div class="row">${this._btn("add-kid", "Ajouter", { cls: "btn primary" })}${this._btn("adding", "Annuler", { cls: "btn" })}</div></div>`
      : this._btn("adding", "+ Ajouter un enfant", { arg: "kid", cls: "link" });
    const list = `<div class="list">${d.kids.map((_, i) => this._kidItem(i)).join("")}${adding}</div>`;
    if (!kid) return `<div class="cols"><div class="side">${list}</div><div class="card mut">Aucun enfant : ajoutez-en un.</div></div>`;
    const p = `kids.${this._kid}`;
    return `<div class="cols">
      <div class="side">${list}${this._identity(kid, p)}</div>
      <div>
        ${this._dayCard(kid, p)}
        <div class="duo">${this._servicesCard(kid)}${this._modesCard(kid)}</div>
        <div class="sensitive">${this._btn("del-kid", "Supprimer cet enfant", { cls: "quiet danger", icon: "mdi:delete-outline", confirmKey: `del-kid:${kid.id}` })}</div>
      </div>
    </div>`;
  },

  _identity(kid, p) {
    const color = L.safeColor(kid.color);
    const known = KID_COLORS.some((c) => c.value.toLowerCase() === String(kid.color ?? "").toLowerCase());
    const colors = `<option value="" ${kid.color ? "" : "selected"}>Aucune</option>
      ${kid.color && !known ? opt(kid.color, `Personnalisée (${kid.color})`, kid.color) : ""}
      ${KID_COLORS.map((c) => `<option value="${c.value}" ${c.value.toLowerCase() === String(kid.color ?? "").toLowerCase() ? "selected" : ""}>${esc(c.label)}</option>`).join("")}`;
    const calendars = this._entities("calendar.");
    const cal = kid.calendar ?? "";
    const calOptions = `<option value="" ${cal ? "" : "selected"}>Aucun (école lun.–ven.)</option>
      ${cal && !calendars.includes(cal) ? opt(cal, `${cal} (introuvable)`, cal) : ""}
      ${calendars.map((c) => opt(c, this._hass?.states?.[c]?.attributes?.friendly_name || c, cal)).join("")}`;
    const editable = this._newIds.has(`kid:${kid.id}`);
    const id = editable
      ? `<label class="field"><span>Identifiant (modifiable jusqu'à l'enregistrement)</span><input value="${esc(kid.id)}" data-rename="kid:${esc(kid.id)}"></label>`
      : `<div class="mut" style="margin-top:14px">Identifiant : ${esc(kid.id)}</div>`;
    return `<div class="card"><h2>Identité</h2>
      <label class="field"><span>Prénom</span><input data-path="${p}.name" value="${esc(kid.name)}"></label>
      <div class="pair" style="margin-top:14px">
        <label class="field"><span>Emoji</span><input data-path="${p}.emoji" value="${esc(kid.emoji ?? "")}" placeholder="🎧"></label>
        <label class="field"><span>Couleur</span><span class="with-dot">
          <span class="dot" style="background:${color ?? "transparent"};${color ? "" : "border:1px solid var(--pc-muted)"}"></span>
          <select data-path="${p}.color">${colors}</select></span></label>
      </div>
      <label class="field" style="margin-top:14px"><span>Calendrier scolaire</span><select data-path="${p}.calendar">${calOptions}</select></label>
      ${id}
    </div>`;
  },

  // Carte « Journée type » : sélecteur de journée, quota, frise à poignées et une ligne par plage.
  _dayCard(kid, p) {
    const dayType = L.DAY_TYPES.find((t) => t.value === this._day) ?? L.DAY_TYPES[0];
    const day = dayType.value;
    const picker = `<span class="seg">${L.DAY_TYPES.map((t) => {
      const own = t.value in kid.profiles;
      const title = own ? "" : "Suit la fin de semaine";
      return `<button type="button" class="${t.value === day ? "on" : ""} ${own ? "" : "dim"}" data-act="day" data-arg="${t.value}" ${title ? `title="${title}"` : ""}>${esc(t.short)}</button>`;
    }).join("")}</span>`;
    const prof = kid.profiles[day];
    if (!prof) {
      return `<div class="card"><h2>Journée type <span class="sp"></span>${picker}</h2>
        <div class="profile-note"><span class="mut">${esc(dayType.label)} : suit la fin de semaine.</span>
          ${this._btn("toggle-profile", "+ Créer son profil propre", { arg: day, cls: "link" })}</div></div>`;
    }
    const pp = `${p}.profiles.${day}`;
    const rows = prof.segments.map((s, i) => this._segRow(s, i, pp, day)).join("");
    const drop = dayType.required ? "" : this._btn("toggle-profile", "Suivre la fin de semaine", { arg: day, cls: "quiet danger", confirmKey: `drop-profile:${kid.id}:${day}` });
    return `<div class="card"><h2>Journée type <span class="sp"></span>${picker}</h2>
      <div class="row quota-row"><span class="mut">Quota d'écran du jour</span>
        <input type="number" min="0" data-type="int" data-path="${pp}.quota_minutes" value="${esc(prof.quota_minutes ?? "")}" placeholder="Aucun" title="Minutes d'écran par jour">
        <span class="mut">min</span><span class="sp"></span><span class="mut">Glisser une limite pour changer l'heure</span></div>
      <div class="tl" data-tl="${pp}">${this._timeline(prof.segments, pp)}</div>
      <div class="ruler">${RULER.map((h) => `<span style="left:${(h / 24) * 100}%">${h === 0 || h === 24 ? `${h} h` : h}</span>`).join("")}</div>
      <div class="segs">${rows}</div>
      <div class="row" style="margin-top:10px">${this._btn("add-seg", "+ Ajouter une plage", { arg: day, cls: "link" })}<span class="sp"></span>${drop}</div>
    </div>`;
  },

  // Intérieur de la frise : plages colorées avec type et horaires, poignées blanches aux limites.
  _timeline(segments, pp) {
    const blocks = L.timelineBlocks(segments);
    const label = (type) => L.SEGMENT_TYPES.find((t) => t.value === type)?.label ?? type;
    const html = blocks.map((b) => `<div class="b" style="left:${b.left}%;width:${b.width}%;background:${pick(SEGMENT_COLORS, b.type, "#666")}"
        title="${esc(label(b.type))} ${b.start} – ${b.end}">${b.width < NARROW ? "" : `<strong>${esc(label(b.type))}</strong><small>${b.start} – ${b.end}</small>`}</div>`).join("");
    const handles = blocks.filter((b) => b.index > 0).map((b) => {
      const bounds = L.segmentBounds(segments, b.index);
      const [hh, mm] = b.start.split(":").map(Number);
      const aria = bounds ? `tabindex="0" role="slider" aria-label="Début de la plage ${b.index + 1}" aria-valuemin="${bounds.min}"
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
        <select data-path="${pp}.segments.${i}.type" title="Type de plage">${L.SEGMENT_TYPES.map((t) => opt(t.value, t.label, s.type)).join("")}</select></span>
      <label class="warn">avertir <input type="number" min="0" data-type="int" data-path="${pp}.segments.${i}.warn_minutes" value="${esc(s.warn_minutes ?? "")}" placeholder="5" title="Avertissement avant la fin de la plage"> min avant</label>
      ${i === 0 ? "<span></span>" : this._btn("del-seg", "", { arg: `${day}:${i}`, icon: "mdi:close", cls: "icon-btn", title: "Retirer cette plage" })}
    </div>`;
  },

  // Carte « Services » : loisirs et services sur demande, pastilles communes puis ajouts de l'enfant.
  _servicesCard(kid) {
    const groups = ["leisure", "on_demand"].map((list) => {
      const [title, sub] = LIST_TITLES[list];
      return `<div class="group"><h3>${title} <span class="mut">(${sub})</span></h3>
        <div class="lz" data-chips="kid:${list}">${this._kidChips(kid, list)}</div></div>`;
    }).join("");
    return `<div class="card"><h2>Services</h2>${groups}
      <div class="mut help">Barré : autorisé pour ${esc(kid.name)} malgré la liste commune. En bleu : ajouté pour ${esc(kid.name)} seulement.</div></div>`;
  },

  // Pastilles d'une liste pour l'enfant, puis le champ « + Ajouter » (redessinées sur place après un ajout).
  _kidChips(kid, list) {
    const chips = L.serviceChips(this._draft, kid, list).map((c) => {
      const title = c.common
        ? c.removed ? `Liste commune : rétablir pour ${kid.name}` : `Liste commune : autoriser pour ${kid.name}`
        : `Propre à ${kid.name} : retirer`;
      return `<button type="button" class="pill ${c.removed ? "off" : ""} ${c.common ? "" : "own"}" data-act="kid-svc" data-list="${list}" data-arg="${esc(c.service)}" title="${esc(title)}">
        ${esc(c.service)}${c.common ? "" : `<span class="x">✕</span>`}</button>`;
    }).join("");
    return `${chips}<input class="pill-in" data-input="kid-svc-${list}" data-enter="add-kid-svc" data-list="${list}" placeholder="+ Ajouter" title="Service AdGuard (ex. fortnite)">`;
  },

  // Carte « Règle par appareil » : contrôle segmenté par appareil de l'enfant.
  _modesCard(kid) {
    const owned = this._draft.resources.filter((r) => (r.owners ?? []).includes(kid.id));
    const rows = owned.map((r) => {
      const current = kid.resource_modes[r.id] ?? "suit_frise";
      return `<div class="mode"><span class="nm"><ha-icon icon="${esc(r.icon || this._resIcon(r))}"></ha-icon><span>${esc(r.name)}</span></span>
        <span class="seg">${L.MODES.map((m) => `<button type="button" class="${m.value === current ? "on" : ""}" data-act="set-mode" data-arg="${m.value}" data-res="${esc(r.id)}" title="${esc(m.label)}">${esc(pick(MODE_SHORT, m.value, m.label))}</button>`).join("")}</span></div>`;
    }).join("");
    return `<div class="card"><h2>Règle par appareil</h2>
      ${rows ? `<div class="modes">${rows}</div>` : `<div class="mut">Aucun appareil : cochez cet enfant dans l'onglet Appareils.</div>`}</div>`;
  },
};
