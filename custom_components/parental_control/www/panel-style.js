// Style et briques HTML partagées du panneau « Règles » (proposition A) : proche de Home Assistant,
// variables du thème de l'utilisateur quand elles existent, valeurs sombres en repli.
import { esc } from "./lib.js";

export const SEGMENT_COLORS = { blocked: "#e0525a", free: "#35b779", after_homework: "#f0a640", quota: "#4a86f0", on_demand: "#7c8591" };

// Couleurs proposées pour un enfant (valeur enregistrée : #rrggbb).
// (`name` : clé `panel.color.<name>` du libellé).
export const KID_COLORS = [
  { value: "#4D96FF", name: "blue" }, { value: "#FF6B6B", name: "red" }, { value: "#6BCB77", name: "green" },
  { value: "#FFA94D", name: "orange" }, { value: "#9775FA", name: "purple" }, { value: "#F783AC", name: "pink" },
  { value: "#FFD43B", name: "yellow" }, { value: "#3BC9DB", name: "turquoise" },
];

// Lecture d'une table de correspondance sans remonter au prototype (« constructor », « toString »…).
export const pick = (map, key, fallback) => (Object.hasOwn(map, key) ? map[key] : fallback);

export const opt = (value, label, current) => `<option value="${esc(value)}" ${value === current ? "selected" : ""}>${esc(label)}</option>`;

export const CSS = `
  :host { display: block; min-height: 100%;
    --pc-bg: var(--primary-background-color, #111316);
    --pc-card: var(--card-background-color, #1b1e23);
    --pc-card2: var(--secondary-background-color, #22262c);
    --pc-text: var(--primary-text-color, #e6e8eb);
    --pc-muted: var(--secondary-text-color, #9aa1ab);
    --pc-line: var(--divider-color, rgba(255,255,255,.08));
    --pc-pri: var(--primary-color, #2fa4e7);
    --pc-sel: color-mix(in srgb, var(--pc-text) 14%, var(--pc-card2));
    --pc-red: #e0525a; --pc-green: #35b779; --pc-amber: #f3b552; --pc-violet: #a78bfa;
    color: var(--pc-text); background: var(--pc-bg);
    font: 14px/1.45 var(--ha-font-family-body, Roboto, "Segoe UI", system-ui, sans-serif); }
  * { box-sizing: border-box; }
  .wrap { padding: 18px 28px 28px; max-width: 1680px; }

  /* En-tête : titre, simulation, onglets en pilules, actions */
  header { display: flex; flex-wrap: wrap; align-items: center; gap: 10px 14px; margin-bottom: 14px; }
  header h1 { font-size: 22px; font-weight: 500; margin: 0; }
  .sim { font-size: 12.5px; color: var(--pc-amber); background: color-mix(in srgb, var(--pc-amber) 12%, transparent);
    padding: 4px 10px; border-radius: 20px; white-space: nowrap; }
  .tabs { display: flex; gap: 4px; margin-left: 24px; }
  .tabs button { padding: 7px 14px; border-radius: 18px; color: var(--pc-muted); }
  .tabs button.on { background: var(--pc-card2); color: var(--pc-text); }
  .sp { flex: 1; }
  .dirty { color: var(--pc-amber); font-size: 12.5px; }
  .ok { color: var(--pc-green); font-size: 12.5px; }

  /* Boutons */
  button { font: inherit; color: inherit; background: none; border: 0; padding: 0; cursor: pointer;
    display: inline-flex; align-items: center; gap: 6px; text-align: left; }
  button:disabled { opacity: .45; cursor: default; }
  button ha-icon { --mdc-icon-size: 18px; }
  button:focus-visible, .h:focus-visible { outline: 2px solid var(--pc-pri); outline-offset: 2px; }
  .btn { padding: 8px 16px; border-radius: 18px; border: 1px solid var(--pc-line); color: var(--pc-muted); font-size: 13px; }
  .btn:not(:disabled):hover { color: var(--pc-text); border-color: color-mix(in srgb, var(--pc-text) 25%, transparent); }
  .btn.primary { background: var(--pc-pri); color: #fff; border-color: transparent; }
  .btn.pending { color: var(--pc-amber); border-color: color-mix(in srgb, var(--pc-amber) 55%, transparent); }
  .btn.primary:not(:disabled):hover { color: #fff; filter: brightness(1.08); }
  .link { color: var(--pc-pri); font-size: 13.5px; }
  .link:hover { text-decoration: underline; }
  .link.danger, .btn.danger { color: var(--pc-red); }
  .quiet { color: var(--pc-muted); font-size: 12.5px; }
  .quiet:hover { color: var(--pc-text); }
  .quiet.danger:hover { color: var(--pc-red); }
  .icon-btn { width: 28px; height: 28px; justify-content: center; border-radius: 8px; color: var(--pc-muted); flex: none; }
  .icon-btn:hover { background: var(--pc-card2); color: var(--pc-text); }
  button.armed, .icon-btn.armed { color: #fff; background: var(--pc-red); border-color: transparent; border-radius: 14px; padding: 4px 10px; width: auto; }

  /* Champs */
  input, select, textarea { font: inherit; font-size: 13.5px; color: var(--pc-text); background: var(--pc-card2);
    border: 1px solid var(--pc-line); border-radius: 10px; padding: 8px 10px; min-width: 0; }
  input:focus, select:focus, textarea:focus { outline: none; border-color: var(--pc-pri); }
  input[readonly] { color: var(--pc-muted); }
  select { cursor: pointer; }
  select option { background: var(--pc-card); color: var(--pc-text); }
  input[type=number] { -moz-appearance: textfield; appearance: textfield; }
  input[type=number]::-webkit-inner-spin-button, input[type=number]::-webkit-outer-spin-button { -webkit-appearance: none; margin: 0; }
  input[type=time]::-webkit-calendar-picker-indicator { display: none; }
  .field { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
  .field > span { font-size: 12px; color: var(--pc-muted); }
  .field + .field, .pair + .field, .field + .pair { margin-top: 14px; }
  .pair { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
  .pair .field + .field, .q .field + .field { margin-top: 0; }
  .with-dot { position: relative; display: flex; }
  .with-dot select { flex: 1; padding-left: 26px; }
  .with-dot .dot { position: absolute; left: 11px; top: 50%; transform: translateY(-50%); pointer-events: none; }
  .icon-field { display: flex; gap: 8px; align-items: center; }
  .icon-field input { flex: 1; }
  .icon-field .preview { width: 36px; height: 36px; border-radius: 10px; display: grid; place-items: center; background: var(--pc-card2); flex: none; }
  label.check { display: flex; align-items: center; gap: 8px; font-size: 13px; }
  label.check input { width: 16px; height: 16px; accent-color: var(--pc-pri); }
  .mut { color: var(--pc-muted); font-size: 12.5px; }
  .row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }

  /* Colonnes : liste à gauche, contenu flexible */
  .cols { display: grid; grid-template-columns: 260px minmax(0, 1fr); gap: 20px; align-items: start; }
  .side { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
  .list { background: var(--pc-card); border-radius: 14px; padding: 8px; display: flex; flex-direction: column; gap: 2px; }
  .it { display: flex; align-items: center; gap: 12px; padding: 10px; border-radius: 10px; width: 100%; }
  .it:hover { background: color-mix(in srgb, var(--pc-card2) 60%, transparent); }
  .it.on { background: var(--pc-card2); }
  .it .n { font-weight: 500; }
  .it .s { font-size: 12px; color: var(--pc-muted); }
  .it > div { min-width: 0; }
  .it .n, .it .s { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .av { width: 34px; height: 34px; border-radius: 50%; display: grid; place-items: center; font-size: 17px; flex: none;
    background: var(--pc-card2); font-weight: 500; }
  .av ha-icon { --mdc-icon-size: 20px; color: var(--pc-muted); }
  .list > .link, .list > .adding { margin: 4px 10px 8px; }
  .adding { display: flex; flex-direction: column; gap: 8px; }
  .adding .row { gap: 8px; }
  .adding input, .adding select { width: 100%; }

  /* Cartes */
  .card { background: var(--pc-card); border-radius: 14px; padding: 18px 20px; margin-bottom: 16px; min-width: 0; }
  .side .card { margin-bottom: 0; }
  .card h2 { font-size: 15px; font-weight: 500; margin: 0 0 12px; display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
  .duo { display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 16px; align-items: stretch; }
  .duo > .card { margin-bottom: 0; }
  .duo + .card, .duo + .sensitive { margin-top: 16px; }

  /* Contrôle segmenté */
  .seg { display: inline-flex; background: var(--pc-card2); border-radius: 10px; padding: 3px; flex-wrap: wrap; }
  .seg button { padding: 6px 12px; border-radius: 8px; color: var(--pc-muted); font-size: 13px; white-space: nowrap; }
  .seg button:hover { color: var(--pc-text); }
  .seg button.on { background: var(--pc-sel); color: var(--pc-text); }
  .seg button.dim { font-style: italic; opacity: .6; }
  .seg button.dim.on { opacity: 1; }

  /* Frise */
  .quota-row { margin-bottom: 8px; }
  .quota-row input { width: 78px; padding: 4px 8px; }
  .tl { position: relative; height: 54px; margin: 6px 0 2px; user-select: none; -webkit-user-select: none; }
  .tl .blocks { position: absolute; inset: 0; border-radius: 10px; overflow: hidden; }
  .tl .b { position: absolute; top: 0; bottom: 0; display: flex; flex-direction: column; justify-content: center;
    padding: 0 10px; color: #fff; font-size: 12.5px; line-height: 1.2; overflow: hidden; border-right: 2px solid var(--pc-card); }
  .tl .b:last-child { border-right: 0; }
  .tl .b strong { font-weight: 500; overflow: hidden; }
  .tl .b small { opacity: .85; font-size: 11px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .tl .h { position: absolute; top: -4px; bottom: -4px; width: 4px; margin-left: -2px; border-radius: 2px; background: #fff;
    cursor: ew-resize; box-shadow: 0 0 0 1px rgba(0,0,0,.25); touch-action: none; }
  .tl .h::before { content: ""; position: absolute; inset: 0 -7px; touch-action: none; }
  .tl .h.fixed { cursor: default; opacity: .5; }
  .tl.dragging, .tl.dragging .h { cursor: ew-resize; }
  .ruler { position: relative; height: 16px; font-size: 11px; color: var(--pc-muted); }
  .ruler span { position: absolute; transform: translateX(-50%); white-space: nowrap; }
  .ruler span:first-child { transform: none; left: 2px !important; }
  .ruler span:last-child { transform: translateX(-100%); }
  .segs { margin-top: 12px; }
  .segrow { display: grid; grid-template-columns: 90px minmax(150px, max-content) 1fr 28px; align-items: center; gap: 12px;
    padding: 6px 6px; border-top: 1px solid var(--pc-line); min-height: 41px; }
  .segrow .t0 { color: var(--pc-muted); padding-left: 6px; }
  .segrow input[type=time] { padding: 4px 8px; width: 90px; }
  .chip { display: inline-flex; align-items: center; gap: 6px; padding: 0 4px 0 10px; border-radius: 14px; background: var(--pc-card2);
    font-size: 12.5px; position: relative; justify-self: start; }
  .chip select { background: transparent; border: 0; padding: 4px 18px 4px 0; appearance: none; -webkit-appearance: none;
    font-size: 12.5px; font-weight: 500; }
  .chip::after { content: "▾"; position: absolute; right: 8px; font-size: 10px; pointer-events: none; color: var(--pc-muted); }
  .dot { width: 9px; height: 9px; border-radius: 50%; display: inline-block; flex: none; }
  .warn { color: var(--pc-muted); font-size: 12.5px; display: flex; align-items: center; gap: 6px; }
  .warn input { width: 52px; padding: 3px 6px; font-size: 12.5px; text-align: center; }
  .segrow .icon-btn { justify-self: end; }
  .profile-note { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; padding: 14px 0 4px; }

  /* Pastilles de services */
  .group + .group, .svc-add + .group { margin-top: 16px; padding-top: 14px; border-top: 1px solid var(--pc-line); }
  .group h3 { font-size: 13px; font-weight: 500; margin: 0 0 8px; }
  .group h3 .mut { font-weight: 400; margin-left: 4px; }
  .lz { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
  .lz .pill { display: inline-flex; align-items: center; gap: 4px; padding: 6px 12px; border-radius: 16px; background: var(--pc-card2);
    font-size: 13px; border: 1px dashed transparent; }
  .lz button.pill:hover { background: var(--pc-sel); }
  .lz .pill.off { text-decoration: line-through; color: var(--pc-muted); background: transparent; border-color: var(--pc-line); }
  .lz .pill.own { background: color-mix(in srgb, var(--pc-pri) 15%, transparent); color: var(--pc-pri); }
  .lz .pill .x { font-size: 11px; opacity: .7; }
  .lz .pill.split { padding: 0 4px 0 12px; }
  .lz .pill.split button { padding: 6px 6px; color: var(--pc-muted); font-size: 12px; }
  .lz .pill.split button:hover { color: var(--pc-text); }
  .lz .pill ha-icon { --mdc-icon-size: 16px; }
  .lz .pill.unk { border-color: var(--pc-red); color: var(--pc-red); }
  .lz .pill .badge { font-size: 11.5px; padding: 1px 7px; border-radius: 10px; }
  .lz .pill .badge.tone-ok { color: var(--pc-green); background: color-mix(in srgb, var(--pc-green) 12%, transparent); }
  .lz .pill .badge.tone-warn { color: var(--pc-amber); background: color-mix(in srgb, var(--pc-amber) 12%, transparent); }
  .lz select.pill-in { width: auto; max-width: 200px; cursor: pointer; color: var(--pc-pri); }
  .lz .pill-in { width: 130px; padding: 6px 12px; border-radius: 16px; font-size: 13px;
    background: color-mix(in srgb, var(--pc-pri) 15%, transparent); border: 1px solid transparent; color: var(--pc-text); }
  .lz .pill-in::placeholder { color: var(--pc-pri); }
  .lz .pill-in:focus { border-color: var(--pc-pri); }

  /* Règle par appareil */
  .modes { display: flex; flex-direction: column; }
  .mode { display: flex; align-items: center; gap: 10px; padding: 7px 0; border-top: 1px solid var(--pc-line); flex-wrap: wrap; }
  .mode .nm { flex: 1 1 120px; display: flex; align-items: center; gap: 8px; min-width: 0; }
  .mode .nm span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .mode .nm ha-icon { --mdc-icon-size: 18px; color: var(--pc-muted); }
  .mode .seg button { padding: 5px 9px; font-size: 12.5px; }

  .sensitive { display: flex; justify-content: flex-end; padding: 4px 4px 0; }

  /* Appareils */
  .res-head h2 { margin-bottom: 14px; }
  .res-head .big { width: 40px; height: 40px; border-radius: 10px; display: grid; place-items: center; background: var(--pc-card2); }
  .res-head .big ha-icon { --mdc-icon-size: 24px; }
  input.title-in { font-size: 18px; font-weight: 500; background: transparent; border-color: transparent; padding: 4px 8px; flex: 1 1 200px; }
  input.title-in:hover { border-color: var(--pc-line); }
  input.title-in:focus { border-color: var(--pc-pri); background: var(--pc-card2); }
  .menu-wrap { position: relative; }
  .menu { position: absolute; right: 0; top: 34px; z-index: 5; width: 300px; padding: 14px; border-radius: 12px;
    background: var(--pc-card2); box-shadow: 0 10px 30px rgba(0,0,0,.45); display: flex; flex-direction: column; gap: 12px; font-size: 13.5px; font-weight: 400; }
  .menu input { background: var(--pc-card); }
  .menu .field + .field { margin-top: 0; }
  .res-cfg { display: flex; gap: 28px; align-items: flex-start; flex-wrap: wrap; }
  .res-cfg > div { min-width: 0; }
  .res-cfg .q-wrap { flex: 1 1 420px; }
  .res-cfg .label { margin-bottom: 6px; }
  .kd { display: flex; flex-wrap: wrap; gap: 6px; }
  .kd button { padding: 5px 11px; border-radius: 16px; font-size: 13px; background: color-mix(in srgb, var(--pc-pri) 15%, transparent);
    color: color-mix(in srgb, var(--pc-pri) 35%, var(--pc-text)); border: 1px solid transparent; }
  .kd button.off { background: transparent; color: var(--pc-muted); border: 1px dashed var(--pc-line); }
  .q { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }
  .q input { width: 100%; }
  .grp { border: 1px solid var(--pc-line); border-radius: 12px; margin-bottom: 12px; }
  .gh { display: flex; align-items: center; gap: 10px; padding: 8px 14px; background: var(--pc-card2); border-radius: 11px 11px 0 0; flex-wrap: wrap; }
  .gh ha-icon { --mdc-icon-size: 20px; color: var(--pc-muted); }
  .gh input { font-weight: 500; background: transparent; border-color: transparent; padding: 4px 6px;
    field-sizing: content; min-width: 80px; max-width: 280px; }
  .gh input:hover { border-color: var(--pc-line); }
  .gh input:focus { border-color: var(--pc-pri); background: var(--pc-card); }
  .gh select.link-select { background: transparent; border: 0; color: var(--pc-muted); font-size: 12.5px; padding: 4px 2px; appearance: none; -webkit-appearance: none; }
  .gh select.link-select:hover { color: var(--pc-text); }
  .gh .sep { color: var(--pc-muted); font-size: 12.5px; }
  .ir { display: grid; grid-template-columns: 28px 150px minmax(0, 1fr) auto 28px; align-items: center; gap: 12px;
    padding: 9px 14px; border-top: 1px solid var(--pc-line); cursor: pointer; }
  .ir:hover { background: color-mix(in srgb, var(--pc-card2) 45%, transparent); }
  .ir.open { background: color-mix(in srgb, var(--pc-card2) 70%, transparent); }
  .ir > ha-icon { --mdc-icon-size: 20px; color: var(--pc-pri); }
  .ty { color: var(--pc-muted); font-size: 12.5px; }
  .ent { font-weight: 500; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .ent.none { font-weight: 400; font-style: italic; color: var(--pc-muted); }
  .ent small { display: block; font-weight: 400; font-style: normal; color: var(--pc-muted); font-size: 12px; overflow: hidden; text-overflow: ellipsis; }
  .st { font-size: 12px; white-space: nowrap; display: inline-flex; align-items: center; gap: 6px; }
  .st.found { color: var(--pc-green); }
  .st.missing { color: var(--pc-red); }
  .st .dot { width: 8px; height: 8px; background: currentColor; }
  .edit { padding: 12px 14px 14px 54px; border-top: 1px dashed var(--pc-line); display: flex; flex-direction: column; gap: 12px;
    background: color-mix(in srgb, var(--pc-card2) 35%, transparent); }
  .edit .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px 14px; }
  .edit .field + .field { margin-top: 0; }
  .edit .field select, .edit .field input { max-width: 520px; }
  .addrow { padding: 10px 14px 10px 54px; border-top: 1px solid var(--pc-line); }
  .addrow select { color: var(--pc-pri); background: transparent; border: 0; padding: 0; font-size: 13px; appearance: none; -webkit-appearance: none; }
  .tree-foot { margin-top: 4px; }

  /* Général */
  .general { display: grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap: 16px; align-items: start; }
  .general .card { margin-bottom: 0; }
  .cal { display: grid; grid-template-columns: minmax(0, 1fr) 200px 28px; gap: 8px 12px; align-items: center; margin: 10px 0; }
  .cal > span { padding: 6px 0; overflow-wrap: anywhere; }
  .help { margin-top: 4px; }
  .btn.danger { border-color: color-mix(in srgb, var(--pc-red) 40%, transparent); }

  /* Services du parent : liste (pastilles AdGuard bleues, labels violets) et édition */
  .svcs { display: flex; flex-direction: column; margin: 10px 0 4px; }
  .svcrow { width: 100%; gap: 12px; padding: 12px 4px; border-top: 1px solid var(--pc-line); }
  .svcrow:first-child { border-top: 0; }
  .svcrow:hover { background: color-mix(in srgb, var(--pc-card2) 45%, transparent); }
  .svcrow .av { border-radius: 10px; }
  .svcrow .body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 6px; }
  .svcrow .n { font-weight: 500; overflow-wrap: anywhere; }
  .svcrow .chev { --mdc-icon-size: 20px; color: var(--pc-muted); }
  .tags { display: flex; flex-wrap: wrap; gap: 6px; }
  .tag { display: inline-flex; align-items: center; gap: 4px; padding: 3px 9px; border-radius: 12px; font-size: 12.5px;
    background: var(--pc-card2); overflow-wrap: anywhere; }
  .tag ha-icon { --mdc-icon-size: 14px; flex: none; }
  .tag.ag { color: var(--pc-pri); }
  .tag.lb { color: var(--pc-violet); }
  .tag.unk { color: var(--pc-red); }
  .svc-add { margin-top: 6px; }
  .svc-edit h2 > ha-icon { --mdc-icon-size: 22px; color: var(--pc-muted); }
  .svc-id { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 240px); gap: 12px; }
  .svc-id .field + .field { margin-top: 0; }
  .sec { display: flex; align-items: center; gap: 8px; font-weight: 500; margin-top: 20px; padding-bottom: 8px;
    border-bottom: 1px solid var(--pc-line); }
  .sec ha-icon { --mdc-icon-size: 18px; color: var(--pc-muted); }
  .sitem { display: flex; align-items: center; justify-content: space-between; gap: 12px; width: 100%; padding: 9px 0;
    border-bottom: 1px solid var(--pc-line); }
  .sitem > span, .lbinfo { min-width: 0; overflow-wrap: anywhere; }
  .lbinfo { display: flex; flex-direction: column; gap: 4px; }
  .sitem.pick { padding: 9px 4px; }
  .sitem.pick:hover { background: color-mix(in srgb, var(--pc-card2) 45%, transparent); }
  .sitem.pick ha-icon { --mdc-icon-size: 20px; color: var(--pc-pri); }
  .sempty { padding: 8px 0; }
  .sadd { padding: 10px 0 4px; }
  .ag-search { display: flex; flex-direction: column; gap: 6px; align-items: flex-start; }
  .ag-search input { width: 100%; }
  .ag-results { width: 100%; max-height: 320px; overflow-y: auto; }
  select.add-select { color: var(--pc-pri); background: transparent; border: 0; padding: 0; font-size: 13.5px;
    appearance: none; -webkit-appearance: none; max-width: 100%; }
  .svc-btns { justify-content: flex-end; margin-top: 16px; }
  .unk-text { color: var(--pc-red); }
  .lsw { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 2px 12px; padding: 6px 0; border-top: 1px solid var(--pc-line); font-size: 13px; }
  .lsw .nm { overflow-wrap: anywhere; }
  .lsw .mut { grid-column: 1; font-size: 12px; }
  .lsw .st { grid-column: 2; grid-row: 1 / span 2; align-self: center; }
  .lsw.bad .nm { color: color-mix(in srgb, var(--pc-red) 75%, var(--pc-text)); }

  textarea { width: 100%; min-height: 420px; font-family: ui-monospace, Menlo, monospace; font-size: 12.5px; margin: 10px 0; }
  .notice, .error { margin: 0 0 14px; padding: 10px 14px; border-radius: 10px; font-size: 13px; }
  .notice { color: var(--pc-amber); background: color-mix(in srgb, var(--pc-amber) 12%, transparent); }
  .error { color: var(--error-color, #ffb4b4); background: color-mix(in srgb, var(--error-color, #e0525a) 16%, transparent); white-space: pre-wrap; }
  input[aria-invalid="true"] { border-color: var(--error-color, #e0525a); }

  @media (max-width: 1100px) {
    .tabs { margin-left: 0; }
    .ir { grid-template-columns: 28px minmax(0, 1fr) auto 28px; }
    .ir .ty { display: none; }
    .general { grid-template-columns: 1fr; }
  }
  @media (max-width: 760px) {
    .wrap { padding: 14px 12px; }
    .cols { grid-template-columns: minmax(0, 1fr); }
    .duo { grid-template-columns: minmax(0, 1fr); }
    .q { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .segrow { grid-template-columns: 80px 1fr 28px; }
    .segrow .warn { grid-column: 1 / -1; grid-row: 2; }
    .edit, .addrow { padding-left: 14px; }
    .svc-id { grid-template-columns: minmax(0, 1fr); }
  }
`;
