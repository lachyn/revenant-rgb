// @ts-check
// Web UI for revenant. Plain JS with JSDoc types: no build step, but `npx tsc -p revenant_web` type-checks it.
//
// Two concepts: the sidebar shows the profiles (saved snapshots) and the active one's state (saved / unsaved);
// the editor changes the current settings, which are sent to the keyboard right away and saved to a profile only
// when the user clicks Save.
"use strict";

/**
 * @typedef {{mode: "effect" | "keys", effect: string, color: string, rainbow: boolean, brightness: number,
 *   speed: number, direction: string, keys: Record<string, string>, base: string, key_brightness: number}} Lighting
 * @typedef {{enabled: boolean, alt_tab: boolean, alt_f4: boolean, win: boolean}} GameMode
 * @typedef {{lighting: Lighting, remap: Record<string, string>, macros: Record<string, string[]>, gamemode: GameMode}} Profile
 * @typedef {[string, string]} Choice  [label, value]
 * @typedef {{state: "ok" | "missing" | "denied", error: string, setup: "udev" | "macos" | null}} Device
 * @typedef {{version: string, active: string, profile: Profile, profiles: string[], info: Record<string, string>,
 *   device: Device, rows: Array<Array<[string | null, number]>>, labels: Record<string, string>, palette: string[],
 *   groups: Record<string, string[]>, keys: string[], effects: Choice[], funcTypes: Choice[],
 *   funcHints: Record<string, string>, macroModes: Choice[], lang: string, languages: Record<string, string>,
 *   langSetting: string, systemLang: string, strings: Record<string, string>, dirty: boolean}} State
 * @typedef {{ok?: boolean, msg?: string, level?: "ok" | "warn", error?: string, state?: State}} Reply
 * @typedef {"lighting" | "keys" | "gamemode"} Part
 */

/** @type {State} */ let S;
/** @type {Profile} */ let P;              // working copy of the current settings
/** @type {Set<string>} */ const selected = new Set();
let current = "ff0000";
let picking = false;
/** @type {string | null} */ let lastClicked = null;
/** @type {string | null} */ let macroName = null;
/** @type {"keys" | "effect"} */ let lightView = "keys";
let remapKey = "caps";

// ------------------------------------------------------------------ i18n
// Source strings are English; the server sends the catalog of the chosen language (revenant_i18n/<lang>.json).

/** translate, then fill {placeholders} @param {string} text @param {Record<string, string | number>} [values] */
function t(text, values) {
  const s = (S && S.strings[text]) || text;
  return values ? s.replace(/\{(\w+)\}/g, (m, k) => (k in values ? String(values[k]) : m)) : s;
}

/** translate the static page: data-i18n text, data-i18n-placeholder / data-i18n-title attributes */
function translatePage() {
  document.documentElement.lang = S.lang;
  for (const el of /** @type {NodeListOf<HTMLElement>} */ (document.querySelectorAll("[data-i18n]"))) {
    el.dataset.i18n ||= (el.textContent || "").replace(/\s+/g, " ").trim();   // remember the English source once
    el.textContent = t(el.dataset.i18n);
  }
  for (const attr of ["placeholder", "title"]) {
    for (const el of /** @type {NodeListOf<HTMLElement>} */ (document.querySelectorAll(`[data-i18n-${attr}]`))) {
      el.setAttribute(attr, t(el.getAttribute(`data-i18n-${attr}`) || ""));
    }
  }
}

// ------------------------------------------------------------------ helpers

/**
 * @template {HTMLElement} T
 * @param {string} sel
 * @param {new () => T} [type]
 * @returns {T}
 */
function $(sel, type) {
  const el = document.querySelector(sel);
  if (!el || (type && !(el instanceof type))) throw new Error("missing element " + sel);
  return /** @type {T} */ (el);
}
const input = (/** @type {string} */ s) => $(s, HTMLInputElement);
const select = (/** @type {string} */ s) => $(s, HTMLSelectElement);
const button = (/** @type {string} */ s) => $(s, HTMLButtonElement);

/**
 * @param {string} tag
 * @param {Record<string, string | boolean | ((e: Event) => void)>} [props]
 * @param {Array<Node | string | null | undefined>} kids
 */
function h(tag, props = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (typeof v === "function") el.addEventListener(k.replace(/^on/, ""), v);
    else if (k === "class") el.className = String(v);
    else if (v === true) el.setAttribute(k, "");
    else if (v !== false) el.setAttribute(k, v);
  }
  for (const c of kids) if (c != null) el.append(c);
  return el;
}

/** @param {HTMLSelectElement} el @param {Choice[]} choices */
function fillSelect(el, choices) {
  el.replaceChildren(...choices.map(([label, value]) => h("option", { value }, label)));
}

/** @param {string} hex */
function contrast(hex) {
  const n = parseInt(hex, 16);
  const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  return 0.299 * r + 0.587 * g + 0.114 * b > 140 ? "#0b0e14" : "#ffffff";
}
const isHex = (/** @type {string} */ s) => /^[0-9a-f]{6}$/i.test(s);
const clone = (/** @type {Profile} */ p) => /** @type {Profile} */ (JSON.parse(JSON.stringify(p)));

/** mark one button of a segmented control as selected @param {string} groupSel @param {string} attr @param {string} value */
function segSelect(groupSel, attr, value) {
  for (const b of /** @type {NodeListOf<HTMLElement>} */ (document.querySelectorAll(`${groupSel} [data-${attr}]`))) {
    b.setAttribute("aria-selected", String(b.dataset[attr] === value));
  }
}

/**
 * in-app confirmation dialog (the browser's confirm() looks foreign and blocks the page)
 * @param {{title: string, text?: string, ok: string, danger?: boolean}} o
 * @returns {Promise<boolean>}
 */
function ask(o) {
  const dlg = /** @type {HTMLDialogElement} */ ($("#dlg"));
  $("#toast").classList.remove("show");             // both live at the top; the question wins
  $("#dlg-title").textContent = o.title;
  $("#dlg-text").textContent = o.text || "";
  $("#dlg-text").hidden = !o.text;
  button("#dlg-ok").textContent = o.ok;
  button("#dlg-ok").className = "btn " + (o.danger ? "danger" : "primary");
  button("#dlg-cancel").textContent = t("Cancel");
  return new Promise((resolve) => {
    dlg.addEventListener("close", () => resolve(dlg.returnValue === "ok"), { once: true });
    dlg.returnValue = "";
    dlg.showModal();
    button("#dlg-cancel").focus();
  });
}

let toastTimer = 0;
/** @param {string} msg @param {"ok" | "warn" | "err"} level */
function toast(msg, level = "ok") {
  const el = $("#toast");
  el.textContent = (level === "ok" ? "✔ " : level === "warn" ? "⚠ " : "✘ ") + msg;
  el.className = `toast show ${level}`;
  clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => el.classList.remove("show"), level === "ok" ? 2500 : 6000);
}

// ------------------------------------------------------------------ API

/** @param {string} path @param {object} [body] @returns {Promise<Reply>} */
async function api(path, body) {
  /** @type {Reply} */ let reply;
  try {
    const res = await fetch(path, body === undefined ? { cache: "no-store" } : {
      method: "POST", headers: { "Content-Type": "application/json", "X-Revenant": "1" }, body: JSON.stringify(body),
    });
    reply = await res.json();
  } catch (e) {
    toast(t("The server does not respond – is `revenant web` still running?"), "err");
    return { ok: false };
  }
  if (path === "/api/state") { setState(/** @type {State} */ (reply)); return { ok: true }; }
  if (reply.state) setState(reply.state);
  if (reply.error) toast(reply.error, "err");
  else if (reply.msg) toast(reply.msg, reply.level === "warn" ? "warn" : "ok");
  return reply;
}

/** store the current settings and send the given parts to the keyboard
 * @param {Part[]} parts @param {string} [done] */
const save = (parts, done) => api("/api/save", { profile: P, parts, done });

/** @param {State} st */
function setState(st) {
  const first = !S, langChanged = !S || S.lang !== st.lang;
  S = st;
  P = clone(st.profile);
  if (first) { build(); lightView = P.lighting.mode; }
  if (langChanged) { translatePage(); fillChoices(); }
  render();
}

/** selects whose labels come from the server (translated there) */
function fillChoices() {
  const [fx, type, mode] = [select("#fx-effect"), select("#rm-type"), select("#rm-mode")];
  const values = [fx.value, type.value || "disable", mode.value || "once"];
  fillSelect(fx, S.effects);
  fillSelect(type, S.funcTypes);
  fillSelect(mode, S.macroModes);
  [fx.value, type.value, mode.value] = values;
  const lang = select("#lang");
  fillSelect(lang, [[t("System ({lang})", { lang: S.languages[S.systemLang] }), "auto"],
    ...Object.entries(S.languages).map(([code, name]) => /** @type {Choice} */ ([name, code]))]);
  lang.value = S.langSetting === "auto" ? "auto" : S.lang;      // REVENANT_LANG can override the setting
  updateRemapForm();
}

// ------------------------------------------------------------------ build (once)

function build() {
  $("#version").textContent = "v" + S.version;

  // editor tabs (remember the last one)
  const tabs = /** @type {HTMLButtonElement[]} */ ([...document.querySelectorAll(".editor > nav [data-tab]")]);
  /** @param {string} name */
  const show = (name) => {
    for (const tb of tabs) {
      const on = tb.dataset.tab === name;
      tb.setAttribute("aria-selected", String(on));
      $("#tab-" + tb.dataset.tab).hidden = !on;
    }
    try { localStorage.setItem("revenant.tab", name); } catch { /* private mode */ }
  };
  for (const tb of tabs) tb.addEventListener("click", () => show(tb.dataset.tab || "lighting"));
  let saved = "lighting";
  try { saved = localStorage.getItem("revenant.tab") || "lighting"; } catch { /* ignore */ }
  show(tabs.some((tb) => tb.dataset.tab === saved) ? saved : "lighting");

  button("#banner-btn").addEventListener("click", runSetup);
  setInterval(() => { if (!document.hidden) pollDevice(); }, 4000);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) { pollDevice(); api("/api/state"); }   // pick up changes made from the command line
  });
  select("#lang").addEventListener("change", () => api("/api/lang", { lang: select("#lang").value }));

  buildProfiles();
  buildLighting();
  buildRemap();
  buildMacros();
  buildGameMode();
}

// ------------------------------------------------------------------ profiles (sidebar)

function buildProfiles() {
  button("#save-profile").addEventListener("click", () => api("/api/profile-save", {}));
  button("#discard").addEventListener("click", async () => {
    if (await ask({ title: t("Discard changes?"), text: t("The keyboard goes back to the saved profile '{name}'.", { name: S.active }),
      ok: t("Discard changes"), danger: true })) api("/api/discard", {});
  });
  button("#apply-all").addEventListener("click", () => api("/api/apply", {}));
  const newName = () => {
    const n = input("#pf-name").value.trim();
    if (!n) toast(t("Enter a profile name"), "err");
    return n;
  };
  const after = (/** @type {Reply} */ r) => { if (r.ok) input("#pf-name").value = ""; };
  button("#pf-copy").addEventListener("click", () => { const n = newName(); if (n) api("/api/copy", { name: n }).then(after); });
  button("#pf-new").addEventListener("click", () => { const n = newName(); if (n) api("/api/new", { name: n }).then(after); });
}

/** @param {string} name */
async function loadProfile(name) {
  if (S.dirty && !await ask({ title: t("Load profile '{name}'?", { name }),
    text: t("Unsaved changes to '{active}' will be lost.", { active: S.active }), ok: t("Load profile"), danger: true })) return;
  selected.clear();
  api("/api/use", { name }).then((r) => { if (r.ok) lightView = P.lighting.mode; render(); });
}

function renderProfiles() {
  $("#active-name").textContent = S.active;
  const state = $("#state");
  state.textContent = S.dirty ? t("Unsaved changes") : t("Saved");
  state.className = "badge " + (S.dirty ? "warn" : "ok");
  button("#save-profile").disabled = !S.dirty;
  button("#save-profile").className = "btn " + (S.dirty ? "primary" : "outline");
  button("#discard").disabled = !S.dirty;
  $("#pf-list").replaceChildren(...S.profiles.map((n) => {
    const active = n === S.active;
    return h("li", { class: "profile-row" + (active ? " active" : ""), title: S.info[n] || "" },
      h("button", { class: "name", type: "button", "aria-current": active ? "true" : false,
        onclick: () => { if (!active) loadProfile(n); } }, n),
      active ? h("span", { class: "badge" }, t("active")) : h("button", {
        class: "btn ghost icon del", type: "button", title: t("Delete profile '{name}'", { name: n }),
        "aria-label": t("Delete profile '{name}'", { name: n }),
        onclick: async () => {
          if (await ask({ title: t("Delete profile '{name}'?", { name: n }), text: t("This can't be undone."), ok: t("Delete"), danger: true })) {
            api("/api/delete", { name: n });
          }
        },
      }, "✕"));
  }));
}

// ------------------------------------------------------------------ keyboards (lighting + key functions)

/** @param {HTMLElement} kbd @param {(key: string, e: MouseEvent) => void} onKey */
function buildKeyboard(kbd, onKey) {
  for (const row of S.rows) {
    const r = h("div", { class: "krow" });
    for (const [key, w] of row) {
      const el = key === null ? h("span", { class: "gap" })
        : h("button", { class: "key", type: "button", "data-key": key, title: key,
          onclick: (e) => onKey(key, /** @type {MouseEvent} */ (e)) }, S.labels[key] ?? key.toUpperCase());
      el.style.width = `calc(var(--u) * ${w} - var(--key-gap))`;
      r.append(el);
    }
    kbd.append(r);
  }
}

// ------------------------------------------------------------------ lighting

function buildLighting() {
  for (const b of /** @type {NodeListOf<HTMLElement>} */ (document.querySelectorAll("#light-mode [data-mode]"))) {
    b.addEventListener("click", () => { lightView = b.dataset.mode === "effect" ? "effect" : "keys"; renderLighting(); });
  }

  buildKeyboard($("#kbd"), (key, e) => keyClick(key, e.shiftKey));
  $("#palette").append(...S.palette.map((c) => {
    const b = h("button", { class: "swatch", type: "button", title: "#" + c, "data-color": c, onclick: () => setColor(c, true) });
    b.style.background = "#" + c;
    return b;
  }));
  input("#color-input").addEventListener("input", () => setColor(input("#color-input").value.slice(1), false));
  input("#color-input").addEventListener("change", () => setColor(input("#color-input").value.slice(1), true));
  for (const g of ["all", "letters", "numbers", "fkeys", "wasd", "arrows", "numpad", "nav", "mods"]) {
    $("#groups").append(h("button", { class: "btn outline sm", type: "button", onclick: () => toggleGroup(g) }, g));
  }
  button("#paint").addEventListener("click", () => paint(current));
  button("#blank").addEventListener("click", () => paint("000000"));
  button("#pick").addEventListener("click", () => setPicking(!picking));
  button("#clear-all").addEventListener("click", async () => {
    if (!await ask({ title: t("Turn all keys off?"), text: t("You can go back with Discard changes until you save."),
      ok: t("Turn all off"), danger: true })) return;
    P.lighting.keys = {};
    P.lighting.base = "000000";
    pushKeys(t("All keys turned off"));
  });
  const kb = input("#key-bright");
  kb.addEventListener("input", () => { $("#key-bright-out").textContent = kb.value; });
  kb.addEventListener("change", () => { P.lighting.key_brightness = Number(kb.value); pushKeys(t("Brightness {n}", { n: kb.value })); });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { selected.clear(); setPicking(false); renderKeys(); }
  });

  // effect
  for (const id of ["#fx-bright", "#fx-speed"]) {
    const el = input(id);
    el.addEventListener("input", () => { $(id + "-out").textContent = el.value; });
  }
  input("#fx-rainbow").addEventListener("change", () => { input("#fx-color").disabled = input("#fx-rainbow").checked; });
  for (const b of /** @type {NodeListOf<HTMLElement>} */ (document.querySelectorAll("#fx-dir [data-dir]"))) {
    b.addEventListener("click", () => segSelect("#fx-dir", "dir", b.dataset.dir || "right"));
  }
  button("#fx-apply").addEventListener("click", () => {
    const dir = /** @type {HTMLElement | null} */ (document.querySelector('#fx-dir [aria-selected="true"]'));
    const eff = select("#fx-effect");
    Object.assign(P.lighting, {
      mode: "effect", effect: eff.value, rainbow: input("#fx-rainbow").checked,
      color: input("#fx-color").value.slice(1).toLowerCase(), brightness: Number(input("#fx-bright").value),
      speed: Number(input("#fx-speed").value), direction: dir?.dataset.dir || "right",
    });
    save(["lighting"], t("Effect {name} started", { name: eff.selectedOptions[0]?.text ?? eff.value }));
  });
}

function renderLighting() {
  const L = P.lighting;
  segSelect("#light-mode", "mode", lightView);
  $("#mode-keys").hidden = lightView !== "keys";
  $("#mode-effect").hidden = lightView !== "effect";
  const effectName = S.effects.find(([, v]) => v === L.effect)?.[0] ?? L.effect;
  $("#mode-note").textContent = L.mode === "keys" ? t("The keyboard shows custom colours")
    : t("The keyboard shows the effect {name}", { name: effectName });

  renderKeys();
  input("#key-bright").value = String(L.key_brightness);
  $("#key-bright-out").textContent = String(L.key_brightness);

  select("#fx-effect").value = L.effect;
  input("#fx-rainbow").checked = !!L.rainbow;
  input("#fx-color").value = "#" + L.color;
  input("#fx-color").disabled = !!L.rainbow;
  input("#fx-bright").value = String(L.brightness);
  input("#fx-speed").value = String(L.speed);
  $("#fx-bright-out").textContent = String(L.brightness);
  $("#fx-speed-out").textContent = String(L.speed);
  segSelect("#fx-dir", "dir", L.direction);
}

/** @param {string} k */
const keyColor = (k) => P.lighting.keys[k] ?? P.lighting.base;

/** @param {string} key @param {boolean} shift */
function keyClick(key, shift) {
  if (picking) {
    setPicking(false);
    setColor(keyColor(key), false);
    toast(t("Eyedropper: #{color}", { color: keyColor(key) }));
    return;
  }
  const prev = lastClicked;
  if (shift && prev) {                            // range within the visual row
    const row = S.rows.map((r) => r.map(([k]) => k).filter((k) => k !== null)).find((r) => r.includes(key) && r.includes(prev));
    if (row) {
      const [a, b] = [row.indexOf(prev), row.indexOf(key)].sort((x, y) => x - y);
      for (const k of row.slice(a, b + 1)) if (k) selected.add(k);
      lastClicked = key;
      return selectionChanged(key);
    }
  }
  if (selected.has(key)) selected.delete(key); else selected.add(key);
  lastClicked = key;
  selectionChanged(selected.has(key) ? key : null);
}

/** show the colour of the clicked key (or of a whole selection sharing one colour) as the current colour,
 *  marked in the palette or in "Custom" – nothing is sent
 * @param {string | null} [clicked] */
function selectionChanged(clicked = null) {
  renderKeys();
  const colors = new Set([...selected].map(keyColor));
  if (clicked) setColor(keyColor(clicked), false);
  else if (colors.size === 1) setColor([...colors][0], false);
}

/** @param {string} g */
function toggleGroup(g) {
  const keys = S.groups[g] || [];
  const all = keys.every((k) => selected.has(k));
  for (const k of keys) all ? selected.delete(k) : selected.add(k);
  selectionChanged();
}

/** @param {string} hex @param {boolean} apply  apply = paint the selection right away */
function setColor(hex, apply) {
  if (!isHex(hex)) return;
  current = hex.toLowerCase();
  const cur = $("#current");
  cur.style.background = "#" + current;
  cur.style.color = contrast(current);
  cur.textContent = "#" + current;
  input("#color-input").value = "#" + current;
  for (const s of document.querySelectorAll(".swatch")) s.classList.toggle("active", /** @type {HTMLElement} */ (s).dataset.color === current);
  $("#custom-pick").classList.toggle("active", !S.palette.includes(current));     // a colour outside the palette
  if (apply && selected.size) paint(current);
}

/** @param {boolean} on */
function setPicking(on) {
  picking = on;
  button("#pick").setAttribute("aria-pressed", String(on));
  $("#kbd").classList.toggle("picking", on);
  if (on) toast(t("Eyedropper: click the key whose colour you want to take"));
}

/** @param {string} col */
function paint(col) {
  if (!selected.size) return toast(t("Select keys first (click them or a group)"), "err");
  for (const k of selected) P.lighting.keys[k] = col;
  pushKeys(t("Keys painted: {n}", { n: selected.size }));
}

/** @param {string} done */
function pushKeys(done) {
  const L = P.lighting;
  L.keys = Object.fromEntries(Object.entries(L.keys).filter(([, v]) => v !== L.base));
  L.mode = "keys";
  L.key_brightness = Number(input("#key-bright").value);
  renderKeys();
  save(["lighting"], done);
}

function renderKeys() {
  for (const el of document.querySelectorAll("#kbd .key")) {
    const b = /** @type {HTMLElement} */ (el);
    const k = b.dataset.key || "";
    const c = keyColor(k);
    const off = c === "000000";
    b.classList.toggle("sel", selected.has(k));
    b.style.background = off ? "" : "#" + c;
    b.style.color = off ? "" : contrast(c);
    b.style.setProperty("--glow", off ? "transparent" : "#" + c);
  }
  $("#sel-count").textContent = selected.size ? t("Selected: {n}", { n: selected.size }) : "";
}

// ------------------------------------------------------------------ key functions

function buildRemap() {
  buildKeyboard($("#kbd-remap"), (key) => { remapKey = key; loadRemap(key); });
  fillSelect(select("#rm-key"), S.keys.map((k) => [k, k]));
  select("#rm-key").addEventListener("change", () => { remapKey = select("#rm-key").value; loadRemap(remapKey); });
  select("#rm-type").addEventListener("change", updateRemapForm);
  select("#rm-mode").addEventListener("change", updateRemapForm);
  button("#rm-set").addEventListener("click", () => {
    const key = remapKey, type = select("#rm-type").value, arg = input("#rm-arg").value.trim();
    let spec = type;
    if (type === "macro") {
      const mode = select("#rm-mode").value;
      spec = `macro:${arg}:${mode}` + (mode === "repeat" ? ":" + (input("#rm-count").value || "1") : "");
    } else if (type !== "default" && type !== "disable") {
      if (!arg) return toast(t("Fill in the function parameter"), "err");
      spec = `${type}:${arg}`;
    }
    if (spec === "default") delete P.remap[key];
    else P.remap[key] = spec;
    save(["keys"], `${key} = ${spec}`);
  });
  button("#rm-reset").addEventListener("click", () => {
    if (!(remapKey in P.remap)) return toast(t("{key} has its default function", { key: remapKey }));
    delete P.remap[remapKey];
    save(["keys"], t("{key} has its default function", { key: remapKey }));
  });
  button("#rm-clear").addEventListener("click", async () => {
    if (!Object.keys(P.remap).length) return;
    if (!await ask({ title: t("Reset all keys to their default function?"), ok: t("All to default"), danger: true })) return;
    P.remap = {};
    save(["keys"], t("All keys have their default function"));
  });
}

function updateRemapForm() {
  const type = select("#rm-type").value;
  const arg = input("#rm-arg");
  arg.placeholder = S.funcHints[type] || "";
  arg.disabled = type === "default" || type === "disable";
  if (type === "macro" && !arg.value) arg.value = Object.keys(P.macros)[0] || "";
  $("#rm-macro-row").hidden = type !== "macro";
  input("#rm-count").disabled = select("#rm-mode").value !== "repeat";
}

/** fill the form from the key's current function @param {string} key */
function loadRemap(key) {
  const spec = P.remap[key] || "default";
  const [kind, ...rest] = spec.split(":");
  select("#rm-key").value = key;
  const known = S.funcTypes.some(([, v]) => v === kind);
  select("#rm-type").value = known ? kind : "key";
  input("#rm-arg").value = "";
  if (kind === "macro") {
    input("#rm-arg").value = rest[0] || "";
    select("#rm-mode").value = rest[1] || "once";
    if (rest[2]) input("#rm-count").value = rest[2];
  } else if (kind !== "default" && kind !== "disable") {
    input("#rm-arg").value = known ? rest.join(":") : spec;
  }
  updateRemapForm();
  renderRemap();
}

function renderRemap() {
  for (const el of document.querySelectorAll("#kbd-remap .key")) {
    const b = /** @type {HTMLElement} */ (el);
    const k = b.dataset.key || "";
    b.classList.toggle("mapped", k in P.remap);
    b.classList.toggle("sel", k === remapKey);
  }
  const order = new Map(S.keys.map((k, i) => [k, i]));
  const rows = Object.entries(P.remap).sort(([a], [b]) => (order.get(a) ?? 0) - (order.get(b) ?? 0));
  $("#rm-table tbody").replaceChildren(...rows.map(([k, v]) => h("tr", { onclick: () => { remapKey = k; loadRemap(k); } },
    h("td", {}, h("code", {}, k)), h("td", {}, v),
    h("td", {}, h("button", { class: "btn ghost sm", type: "button", onclick: (e) => {
      e.stopPropagation();
      delete P.remap[k];
      save(["keys"], t("{key} has its default function", { key: k }));
    } }, t("Reset key"))))));
  $("#rm-table").hidden = !rows.length;
  $("#rm-empty").hidden = !!rows.length;
}

// ------------------------------------------------------------------ macros

function buildMacros() {
  button("#mc-new").addEventListener("click", () => {
    const name = input("#mc-name").value.trim();
    if (!name || /[\s:]/.test(name)) return toast(t("Enter a macro name (no spaces or colons)"), "err");
    if (name in P.macros) return toast(t("The macro already exists"), "err");
    P.macros[name] = ["text:" + t("Hello!")];
    input("#mc-name").value = "";
    macroName = name;
    showMacro();
    save(["keys"], t("Macro '{name}' created – edit the steps and save", { name }));
  });
  button("#mc-save").addEventListener("click", () => {
    if (!macroName) return toast(t("Create or select a macro first"), "err");
    const steps = /** @type {HTMLTextAreaElement} */ ($("#mc-edit")).value.split("\n").map((s) => s.trim()).filter(Boolean);
    if (!steps.length) return toast(t("A macro needs at least one step"), "err");
    P.macros[macroName] = steps;
    save(["keys"], t("Macro '{name}' saved ({n} steps)", { name: macroName, n: steps.length }));
  });
  button("#mc-del").addEventListener("click", async () => {
    const name = macroName;
    if (!name) return;
    const used = Object.entries(P.remap).filter(([, v]) => v.split(":")[0] === "macro" && v.split(":")[1] === name);
    if (used.length) return toast(t("The macro is used by keys {keys} – change their function first", { keys: used.map(([k]) => k).join(", ") }), "err");
    if (!await ask({ title: t("Delete macro '{name}'?", { name }), ok: t("Delete"), danger: true })) return;
    delete P.macros[name];
    macroName = null;
    save(["keys"], t("Macro '{name}' deleted", { name })).then(showMacro);
  });
}

function renderMacros() {
  const names = Object.keys(P.macros);
  if (macroName && !names.includes(macroName)) macroName = null;
  if (!macroName && names.length) { macroName = names[0]; showMacro(); }
  $("#mc-list").replaceChildren(...names.map((n) => h("li", {}, h("button", {
    type: "button", class: n === macroName ? "sel" : "", onclick: () => { macroName = n; showMacro(); renderMacros(); },
  }, h("code", {}, n), h("span", { class: "muted" }, t("{n} steps", { n: P.macros[n].length }))))));
  $("#mc-empty").hidden = !!names.length;
  if (!names.length) showMacro();
}

/** load the selected macro into the editor (only on selection change, so unsaved edits survive re-renders) */
function showMacro() {
  const ta = /** @type {HTMLTextAreaElement} */ ($("#mc-edit"));
  ta.value = macroName ? (P.macros[macroName] || []).join("\n") : "";
  ta.disabled = !macroName;
  $("#mc-current").textContent = macroName ? `(${macroName})` : "";
}

// ------------------------------------------------------------------ game mode

function buildGameMode() {
  for (const k of ["enabled", "alt_tab", "alt_f4", "win"]) {
    input("#gm-" + k).addEventListener("change", () => {
      const g = P.gamemode;
      g.enabled = input("#gm-enabled").checked;
      g.alt_tab = input("#gm-alt_tab").checked;
      g.alt_f4 = input("#gm-alt_f4").checked;
      g.win = input("#gm-win").checked;
      save(["gamemode"], g.enabled ? t("Game mode on") : t("Game mode off"));
    });
  }
}

// ------------------------------------------------------------------ render (after every state change)

function render() {
  renderDevice(S.device);
  renderProfiles();
  renderLighting();
  renderRemap();
  renderMacros();
  for (const k of /** @type {const} */ (["enabled", "alt_tab", "alt_f4", "win"])) input("#gm-" + k).checked = P.gamemode[k];
}

// ------------------------------------------------------------------ keyboard access

/** @param {Device} d */
function renderDevice(d) {
  S.device = d;
  const badge = $("#device");
  $("#device-text").textContent = { ok: t("Keyboard connected"), missing: t("Keyboard not found"), denied: t("Keyboard without access") }[d.state];
  badge.title = d.error || t("The keyboard is connected and accessible");
  badge.className = "badge " + (d.state === "ok" ? "ok" : "warn");

  const banner = $("#banner"), btn = button("#banner-btn");
  banner.hidden = d.state === "ok";
  banner.classList.toggle("err", d.state === "denied");
  if (d.state === "missing") {
    $("#banner-title").textContent = t("The keyboard is not connected");
    $("#banner-text").textContent = t("Connect it with the USB cable (switch on the bottom set to Off). Changes are saved meanwhile.");
    btn.hidden = true;
  } else if (d.state === "denied") {
    $("#banner-title").textContent = t("The keyboard is connected, but the program has no access to it");
    const hint = d.setup === "udev" ? t("On Linux a udev rule has to be installed once – it asks for the administrator password.")
      : d.setup === "macos" ? t("macOS requires the Input Monitoring permission for the app revenant runs from.")
      : t("Close the original CZC program and try again.");
    $("#banner-text").textContent = hint + "\n" + d.error;
    btn.hidden = !d.setup;
    btn.textContent = d.setup === "macos" ? t("Open settings") : t("Set up access");
  }
}

let polling = false;
async function pollDevice() {
  if (polling) return;
  polling = true;
  try {
    const res = await fetch("/api/device", { cache: "no-store" });
    if (res.ok) renderDevice(/** @type {Device} */ (await res.json()));
  } catch { /* server stopped; api() reports it on the next action */ }
  polling = false;
}

async function runSetup() {
  const btn = button("#banner-btn");
  btn.disabled = true;
  const label = btn.textContent;
  btn.textContent = t("Waiting for the password…");
  try { await api("/api/setup", {}); } finally { btn.disabled = false; btn.textContent = label; }
}

// ------------------------------------------------------------------ start

api("/api/state").then(() => setColor(current, false));
