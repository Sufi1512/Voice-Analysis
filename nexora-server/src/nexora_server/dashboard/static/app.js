// Nexora Voice Cloud admin dashboard (E8). No framework, no third-party code.
// Every value from the API is put on the page with textContent, never as HTML.
// English and Arabic (right to left): every visible string goes through t() (i18n.js).

import { LANGS, lang, locale, setLang, t } from "./i18n.js";

const KEY_STORE = "nexora.dashboard.key"; // sessionStorage: gone when the tab closes
const state = { me: null, org: null, orgs: [] };

// ---- tiny DOM helper -------------------------------------------------------------------

export function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "class") el.className = v;
    else el.setAttribute(k, v === true ? "" : String(v));
  }
  for (const kid of kids.flat()) {
    if (kid === null || kid === undefined || kid === false) continue;
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

const $ = (sel) => document.querySelector(sel);
const fmtDate = (s) => (s ? new Date(s).toLocaleString(locale()) : "");
const fmtMin = (m) => (m >= 100 ? Math.round(m).toLocaleString(locale()) : m.toFixed(1));

// a translated sentence with elements in it: tpl("Use the {scope} scope", {scope: node})
function tpl(text, nodes) {
  return text.split(/(\{\w+\})/).map((part) => {
    const m = /^\{(\w+)\}$/.exec(part);
    return m && nodes[m[1]] ? nodes[m[1]] : part;
  });
}

// a data table with a caption and column headers for screen readers, scrollable on its
// own (by keyboard too) when it is wider than the screen
function table(caption, headers, rows) {
  return h(
    "div",
    { class: "table-wrap", role: "region", "aria-label": caption, tabindex: 0 },
    h(
      "table",
      {},
      h("caption", { class: "sr-only" }, caption),
      h("thead", {}, h("tr", {}, headers.map((x) => h("th", { scope: "col" }, x)))),
      h("tbody", {}, rows),
    ),
  );
}

function pill(status, good) {
  return h("span", { class: `pill ${good === undefined ? "" : good ? "good" : "bad"}` }, t(status));
}

// ---- API -------------------------------------------------------------------------------

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

async function api(method, path, body) {
  const headers = { Accept: "application/json" };
  const key = sessionStorage.getItem(KEY_STORE);
  if (key) headers.Authorization = `Bearer ${key}`;
  else headers["X-Nexora-CSRF"] = "1"; // SSO cookie sessions (E9) need this on every call
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const url = new URL(path, location.origin);
  if (state.me?.superadmin && state.org && !url.pathname.startsWith("/v1/orgs") && url.pathname !== "/v1/me") {
    if (method === "GET" || method === "DELETE") url.searchParams.set("org_id", state.org);
  }
  const res = await fetch(url, {
    method,
    headers,
    credentials: "same-origin",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail ?? data);
    throw new ApiError(res.status, detail || res.statusText);
  }
  return data;
}

// superadmin calls that create things name the organization in the body
const withOrg = (body) => (state.me?.superadmin ? { ...body, org_id: state.org } : body);

// ---- shell -----------------------------------------------------------------------------

function showSignin(message = "") {
  $("#signin").hidden = false;
  $("#nav").hidden = true;
  $("#signout").hidden = true;
  $("#who").textContent = "";
  $("#view").replaceChildren();
  $("#signin-error").textContent = message;
}

// text in index.html: data-i18n (text) and data-i18n-label (aria-label)
function translatePage() {
  for (const el of document.querySelectorAll("[data-i18n]")) el.textContent = t(el.dataset.i18n);
  for (const el of document.querySelectorAll("[data-i18n-label]")) el.setAttribute("aria-label", t(el.dataset.i18nLabel));
  $("#signin-help").replaceChildren(...tpl(t("Paste an API key with the {scope} scope. It is kept only in this browser tab."), { scope: h("code", {}, "admin") }));
  const pick = $("#lang");
  pick.replaceChildren(...LANGS.map(([code, name]) => h("option", { value: code, selected: code === lang, lang: code }, name)));
}

async function start() {
  setLang(lang, false);
  translatePage();
  $("#lang").addEventListener("change", (e) => {
    setLang(e.target.value);
    translatePage();
    if (state.me) {
      $("#who").textContent = state.me.superadmin ? t("super-admin") : state.me.org_name || state.me.org_id;
      if (state.me.superadmin) fillOrgPick();
      render();
    }
  });
  $("#signin-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    sessionStorage.setItem(KEY_STORE, $("#signin-key").value.trim());
    $("#signin-key").value = "";
    await boot();
  });
  $("#signout").addEventListener("click", async () => {
    sessionStorage.removeItem(KEY_STORE);
    await fetch("/auth/logout", { method: "POST", credentials: "same-origin", headers: { "X-Nexora-CSRF": "1" } }).catch(() => {});
    state.me = null;
    showSignin();
  });
  window.addEventListener("hashchange", render);
  fetch("/auth/oidc/status").then((r) => (r.ok ? r.json() : null)).then((s) => {
    if (s?.enabled) $("#sso").hidden = false;
  }).catch(() => {});
  await boot();
}

async function boot() {
  try {
    state.me = await api("GET", "/v1/me");
  } catch (err) {
    sessionStorage.removeItem(KEY_STORE);
    showSignin(err instanceof ApiError && err.status !== 401 ? err.message : "");
    return;
  }
  if (!state.me.superadmin && !state.me.scopes.includes("admin")) {
    sessionStorage.removeItem(KEY_STORE);
    showSignin(t("This key does not have the admin scope."));
    return;
  }
  $("#signin").hidden = true;
  $("#nav").hidden = false;
  $("#signout").hidden = false;
  $("#who").textContent = state.me.superadmin ? t("super-admin") : state.me.org_name || state.me.org_id;
  for (const el of document.querySelectorAll("[data-superadmin]")) el.hidden = !state.me.superadmin;
  if (state.me.superadmin) await loadOrgs();
  else state.org = state.me.org_id;
  if (!location.hash) location.hash = state.me.superadmin ? "#/orgs" : "#/overview";
  await render();
}

async function loadOrgs() {
  state.orgs = await api("GET", "/v1/orgs");
  fillOrgPick();
}

function fillOrgPick() {
  const pick = $("#org-pick");
  pick.replaceChildren(
    h("option", { value: "" }, t("Choose an organization")),
    ...state.orgs.map((o) => h("option", { value: o.id, selected: o.id === state.org }, o.name)),
  );
  pick.onchange = () => {
    state.org = pick.value || null;
    render();
  };
}

const VIEWS = { overview, keys, profiles, sessions, team, billing, audit, orgs };
const TITLES = { overview: "Overview", keys: "API keys", profiles: "Profiles", sessions: "Sessions", team: "Team", billing: "Billing", audit: "Audit log", orgs: "Organizations" };

async function render() {
  if (!state.me) return;
  let name = (location.hash.replace(/^#\//, "") || "overview").split("/")[0];
  if (!VIEWS[name]) name = "overview";
  for (const a of document.querySelectorAll("nav a")) {
    const here = a.getAttribute("href") === `#/${name}`;
    a.classList.toggle("active", here);
    if (here) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  }
  document.title = `${t(TITLES[name])} - ${t("Nexora Voice Cloud")}`;
  const view = VIEWS[name];
  const root = $("#view");
  if (view !== orgs && state.me.superadmin && !state.org) {
    root.replaceChildren(h("div", { class: "card" }, h("p", {}, t("Choose an organization at the top right."))));
    return;
  }
  root.setAttribute("aria-busy", "true");
  root.replaceChildren(h("p", { class: "muted" }, t("Loading...")));
  try {
    root.replaceChildren(await view());
  } catch (err) {
    root.replaceChildren(h("div", { class: "card" }, h("p", { class: "error", role: "alert" }, err.message)));
  }
  root.removeAttribute("aria-busy");
  // keyboard and screen-reader users land on the new page's heading, not back at the top
  const heading = root.querySelector("h1");
  if (heading && !document.querySelector("dialog[open]")) {
    heading.tabIndex = -1;
    heading.focus({ preventScroll: true });
  }
}

function dialog(title, body, actions) {
  // a fresh <dialog> each time: a closing dialog's late "close" event can never reach the
  // next one (that once blanked a new API key before it could be copied)
  for (const old of document.querySelectorAll("dialog.closing")) old.remove();
  const id = `dlg-${Math.random().toString(36).slice(2)}`;
  const d = h("dialog", { class: "modal", "aria-labelledby": id }, h("form", { method: "dialog" }, h("h2", { id }, title), body, h("div", { class: "row" }, h("span"), h("div", {}, ...actions))));
  d.addEventListener("close", () => {
    d.classList.add("closing");
    setTimeout(() => d.remove(), 0);
  });
  document.body.append(d);
  d.showModal();
  return d;
}

// ---- overview --------------------------------------------------------------------------

export function barChart(days) {
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("class", "chart");
  svg.setAttribute("viewBox", "0 0 600 220");
  svg.setAttribute("preserveAspectRatio", "xMinYMid meet");
  svg.setAttribute("role", "img");
  const max = Math.max(1, ...days.map((d) => d.audio_minutes));
  const busiest = days.reduce((a, d) => (d.audio_minutes > (a?.audio_minutes ?? -1) ? d : a), null);
  const total = days.reduce((a, d) => a + d.audio_minutes, 0);
  svg.setAttribute(
    "aria-label",
    `${t("Audio minutes per day")}: ${t("{days} days, {total} minutes in total; busiest day {date} with {max} minutes.", { days: days.length, total: fmtMin(total), date: busiest?.date ?? "", max: fmtMin(busiest?.audio_minutes ?? 0) })}`,
  );
  const w = 560 / Math.max(days.length, 1);
  const el = (tag, attrs, text) => {
    const e = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, String(v));
    if (text !== undefined) e.textContent = text;
    svg.append(e);
    return e;
  };
  el("line", { x1: 30, y1: 190, x2: 590, y2: 190 });
  el("text", { x: 0, y: 14 }, t("{n} min", { n: fmtMin(max) }));
  days.forEach((d, i) => {
    const bh = (d.audio_minutes / max) * 170;
    const rect = el("rect", { x: 32 + i * w, y: 190 - bh, width: Math.max(w - 3, 1), height: bh, rx: 2 });
    const tip = document.createElementNS(NS, "title");
    tip.textContent = t("{date}: {min} min, {n} sessions", { date: d.date, min: fmtMin(d.audio_minutes), n: d.sessions });
    rect.append(tip);
    if (i % 7 === 0 || i === days.length - 1) {
      el("text", { x: 32 + i * w, y: 208 }, String(d.date).slice(5));
    }
  });
  return svg;
}

async function overview() {
  const [usage, org] = await Promise.all([api("GET", "/v1/usage"), api("GET", `/v1/orgs/${state.org}`)]);
  const quota = usage.monthly_minutes_quota;
  const used = usage.month_to_date_minutes;
  const pct = quota ? Math.min(100, (100 * used) / quota) : 0;
  return h(
    "div",
    {},
    h("h1", { dir: "auto" }, org.name),
    h(
      "div",
      { class: "tiles" },
      tile(fmtMin(used), t("minutes this month")),
      tile(quota ? `${Math.round(pct)}%` : t("none"), quota ? t("of {quota} minute quota", { quota: quota.toLocaleString(locale()) }) : t("monthly quota")),
      tile(String(usage.sessions), t("sessions, last 30 days")),
      tile(`${usage.active_sessions} / ${org.max_concurrent_sessions}`, t("calls right now / allowed at once")),
    ),
    quota ? h("div", { class: "card" }, meter(pct, t("{used} of {quota} minutes used", { used: fmtMin(used), quota }))) : null,
    h("div", { class: "card" }, h("h2", {}, t("Audio minutes per day (last 30 days, by the day each call ended)")), usage.days.length ? barChart(fillDays(usage.days, new Date(usage.period_start), new Date(usage.period_end))) : h("p", { class: "muted" }, t("No sessions yet."))),
    h("div", { class: "card" }, h("h2", {}, t("Relay allowlist")), org.relay_allowlist.length ? h("ul", {}, org.relay_allowlist.map((x) => h("li", { class: "mono" }, x))) : h("p", { class: "muted" }, t("Empty: Relay mode is off for this organization."))),
  );
}

// one bar per calendar day (UTC) in the period, zero when there were no calls
export function fillDays(days, start, end) {
  const byDate = new Map(days.map((d) => [String(d.date), d]));
  const out = [];
  const day = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth(), start.getUTCDate()));
  while (day <= end) {
    const key = day.toISOString().slice(0, 10);
    out.push(byDate.get(key) ?? { date: key, audio_minutes: 0, sessions: 0 });
    day.setUTCDate(day.getUTCDate() + 1);
  }
  return out;
}

function meter(pct, text) {
  const bar = h("span");
  bar.style.width = `${pct}%`; // CSSOM, allowed by the CSP (inline style attributes are not)
  const id = `meter-${Math.random().toString(36).slice(2)}`;
  return h(
    "div",
    {},
    h("div", { class: "meter", role: "meter", "aria-valuenow": Math.round(pct), "aria-valuemin": 0, "aria-valuemax": 100, "aria-labelledby": id }, bar),
    h("p", { class: "muted", id }, text),
  );
}

function tile(num, label) {
  return h("div", { class: "card tile" }, h("div", { class: "num" }, num), h("div", { class: "label" }, label));
}

// ---- API keys --------------------------------------------------------------------------

const SCOPES = ["stream", "admin", "usage:read"];

async function keys() {
  const list = await api("GET", "/v1/keys");
  const rows = list.map((k) => h(
    "tr",
    {},
    h("td", { dir: k.name ? "auto" : null }, k.name || h("span", { class: "muted" }, t("(no name)"))),
    h("td", { class: "mono" }, `${k.prefix}...`),
    h("td", { class: "mono" }, k.scopes.join(", ")),
    h("td", {}, fmtDate(k.created_at)),
    h("td", {}, k.last_used_at ? fmtDate(k.last_used_at) : h("span", { class: "muted" }, t("never"))),
    h("td", {}, k.revoked_at ? pill("revoked", false) : h("button", { class: "danger", "aria-label": t("Revoke key {name}", { name: k.name || k.prefix }), onclick: () => revokeKey(k) }, t("Revoke"))),
  ));
  return h(
    "div",
    {},
    h("div", { class: "row" }, h("h1", {}, t("API keys")), h("button", { onclick: newKey }, t("New key"))),
    h("div", { class: "card" }, table(t("API keys"), [t("Name"), t("Key"), t("Scopes"), t("Created"), t("Last used"), t("Actions")], rows)),
  );
}

function newKey() {
  const name = h("input", { type: "text", maxlength: 200, placeholder: t("e.g. production agents") });
  const boxes = SCOPES.map((sc) => h("input", { type: "checkbox", value: sc, checked: sc === "stream" }));
  const err = h("p", { class: "error", role: "alert" });
  const body = h("div", {}, h("label", {}, `${t("Name")} `, name), h("fieldset", {}, h("legend", {}, t("Scopes")), ...SCOPES.map((sc, i) => h("label", { class: "check mono" }, boxes[i], sc))), err);
  const d = dialog(t("New API key"), body, [
    h("button", { class: "secondary", value: "cancel" }, t("Cancel")),
    h("button", {
      onclick: async (e) => {
        e.preventDefault();
        try {
          const scopes = boxes.filter((b) => b.checked).map((b) => b.value);
          const res = await api("POST", "/v1/keys", withOrg({ name: name.value, scopes }));
          d.close();
          showSecret(res.api_key);
        } catch (ex) {
          err.textContent = ex.message;
        }
      },
    }, t("Create")),
  ]);
}

function showSecret(secret) {
  const box = h("div", { class: "secret mono" }, secret);
  const d = dialog(t("Copy your new key now"), h("div", {}, h("p", {}, t("It will not be shown again. Store it in your secrets manager.")), box), [
    h("button", { class: "secondary", onclick: (e) => { e.preventDefault(); navigator.clipboard?.writeText(secret); } }, t("Copy")),
    h("button", { value: "done" }, t("Done")),
  ]);
  d.addEventListener("close", () => { box.textContent = ""; render(); }, { once: true });
}

function revokeKey(k) {
  const d = dialog(t("Revoke {name}?", { name: k.name || k.prefix }), h("p", {}, t("Anything using this key stops working at once. This cannot be undone.")), [
    h("button", { class: "secondary", value: "cancel" }, t("Cancel")),
    h("button", { class: "danger", onclick: async (e) => { e.preventDefault(); await api("DELETE", `/v1/keys/${k.id}`); d.close(); render(); } }, t("Revoke")),
  ]);
}

// ---- profiles --------------------------------------------------------------------------

const AUDIO_FIELDS = [
  ["noise_cancellation", "bool", "Noise removal"],
  ["noise_backend", ["auto", "deepfilternet3", "rnnoise", "webrtc"], "Noise engine"],
  ["echo_cancellation", "bool", "Echo cancellation (speakerphone callers)"],
  ["speech_guard", "bool", "Speech guard (never cut speech on phone lines)"],
  ["background_speech_db", "number", "Background talker gate, dB below the caller (empty: off)"],
  ["voice_enhancement", "bool", "Voice enhancement"],
  ["auto_gain_control", "bool", "Automatic gain"],
];
const TURN_FIELDS = [
  ["smart_turn", "bool", "Smart Turn (learned end of turn)"],
  ["text_cue", "bool", "Transcript cue (\"...to\", \"um\" wait longer)"],
  ["complete_silence_ms", "number", "Silence before replying when the caller sounds finished (ms)"],
  ["incomplete_silence_ms", "number", "Silence before replying when unfinished (ms)"],
  ["end_of_turn_ms", "number", "Silence before replying without a verdict (ms)"],
  ["interruption_min_ms", "number", "Caller speech needed to interrupt the agent (ms)"],
];

function fieldInputs(fields, values) {
  const inputs = {};
  const els = fields.map(([name, type, label]) => {
    const v = values?.[name];
    let input;
    if (type === "bool") {
      input = h("input", { type: "checkbox", checked: v === undefined ? null : Boolean(v), "data-unset": v === undefined ? "1" : null });
      input.indeterminate = v === undefined;
      return [name, h("label", { class: "check" }, (inputs[name] = input), t(label), v === undefined ? h("span", { class: "muted" }, ` ${t("(default)")}`) : null)];
    }
    if (Array.isArray(type)) {
      input = h("select", {}, h("option", { value: "" }, t("(default)")), type.map((o) => h("option", { value: o, selected: v === o }, o)));
    } else {
      input = h("input", { type: "number", step: "any", value: v ?? "" });
    }
    return [name, h("label", {}, t(label), " ", (inputs[name] = input))];
  });
  return { inputs, els: els.map((x) => x[1]) };
}

function collect(fields, inputs) {
  const out = {};
  for (const [name, type] of fields) {
    const el = inputs[name];
    if (type === "bool") {
      if (!el.indeterminate) out[name] = el.checked;
    } else if (el.value !== "") {
      out[name] = Array.isArray(type) ? el.value : Number(el.value);
    }
  }
  return out;
}

async function profiles() {
  const list = await api("GET", "/v1/profiles");
  return h(
    "div",
    {},
    h("div", { class: "row" }, h("h1", {}, t("Profiles")), h("button", { onclick: () => editProfile(null) }, t("New profile"))),
    h("p", { class: "muted" }, t("A profile is a named set of audio and turn-taking settings; clients pick one with ?profile=name.")),
    h("div", { class: "card" }, list.length ? table(t("Profiles"), [t("Name"), t("Audio"), t("Turns"), t("Updated"), t("Actions")], list.map((p) => h(
      "tr",
      {},
      h("td", {}, h("bdi", {}, p.name), p.is_default ? [" ", pill("default", true)] : null),
      h("td", { class: "mono wrap" }, JSON.stringify(p.audio_settings)),
      h("td", { class: "mono wrap" }, p.turn_settings === null ? t("off") : JSON.stringify(p.turn_settings)),
      h("td", {}, fmtDate(p.updated_at)),
      h("td", {}, h("button", { class: "secondary", "aria-label": t("Edit {name}", { name: p.name }), onclick: () => editProfile(p) }, t("Edit")), " ", h("button", { class: "danger", "aria-label": t("Delete {name}", { name: p.name }), onclick: () => deleteProfile(p) }, t("Delete"))),
    ))) : h("p", { class: "muted" }, t("No profiles yet: every session uses the built-in defaults."))),
  );
}

function editProfile(p) {
  const name = h("input", { type: "text", value: p?.name ?? "", pattern: "[A-Za-z0-9_.-]+", required: true, disabled: p ? true : null });
  const audio = fieldInputs(AUDIO_FIELDS, p?.audio_settings);
  const turns = fieldInputs(TURN_FIELDS, p?.turn_settings ?? undefined);
  const noTurns = h("input", { type: "checkbox", checked: p ? p.turn_settings === null : null });
  const isDefault = h("input", { type: "checkbox", checked: p?.is_default ?? null });
  const known = new Set([...AUDIO_FIELDS, ...TURN_FIELDS].map((f) => f[0]));
  const extra = (o) => Object.fromEntries(Object.entries(o || {}).filter(([k]) => !known.has(k)));
  const advAudio = h("textarea", {}, JSON.stringify(extra(p?.audio_settings), null, 1));
  const advTurns = h("textarea", {}, JSON.stringify(extra(p?.turn_settings), null, 1));
  const err = h("p", { class: "error", role: "alert" });
  const body = h(
    "div",
    {},
    h("label", {}, `${t("Name")} `, name),
    h("div", { class: "grid2" }, h("fieldset", {}, h("legend", {}, t("Audio")), audio.els, h("label", {}, `${t("Other audio settings (JSON)")} `, advAudio)), h("fieldset", {}, h("legend", {}, t("Turn-taking")), h("label", { class: "check" }, noTurns, t("No turn events")), turns.els, h("label", {}, `${t("Other turn settings (JSON)")} `, advTurns))),
    h("label", { class: "check" }, isDefault, t("Default profile")),
    err,
  );
  const d = dialog(p ? t("Edit {name}", { name: p.name }) : t("New profile"), body, [
    h("button", { class: "secondary", value: "cancel" }, t("Cancel")),
    h("button", {
      onclick: async (e) => {
        e.preventDefault();
        try {
          const audioSettings = { ...JSON.parse(advAudio.value || "{}"), ...collect(AUDIO_FIELDS, audio.inputs) };
          const turnSettings = { ...JSON.parse(advTurns.value || "{}"), ...collect(TURN_FIELDS, turns.inputs) };
          if (p) {
            await api("PATCH", `/v1/profiles/${p.id}`, { audio_settings: audioSettings, turn_settings: noTurns.checked ? null : turnSettings, disable_turns: noTurns.checked, is_default: isDefault.checked });
          } else {
            await api("POST", "/v1/profiles", withOrg({ name: name.value, audio_settings: audioSettings, turn_settings: noTurns.checked ? null : turnSettings, is_default: isDefault.checked }));
          }
          d.close();
          render();
        } catch (ex) {
          err.textContent = ex instanceof SyntaxError ? t("Invalid JSON: {msg}", { msg: ex.message }) : ex.message;
        }
      },
    }, t("Save")),
  ]);
}

function deleteProfile(p) {
  const d = dialog(t("Delete {name}?", { name: p.name }), h("p", {}, t("Clients that ask for this profile will be refused.")), [
    h("button", { class: "secondary", value: "cancel" }, t("Cancel")),
    h("button", { class: "danger", onclick: async (e) => { e.preventDefault(); await api("DELETE", `/v1/profiles/${p.id}`); d.close(); render(); } }, t("Delete")),
  ]);
}

// ---- sessions --------------------------------------------------------------------------

async function sessions() {
  const list = await api("GET", "/v1/sessions?limit=100");
  const q = (s, k) => (s.quality && s.quality[k] !== undefined && s.quality[k] !== null ? s.quality[k] : "");
  return h(
    "div",
    {},
    h("div", { class: "row" }, h("h1", {}, t("Recent sessions")), exportButtons("/v1/sessions/export", "sessions")),
    h("div", { class: "card" }, list.length ? table(t("Recent sessions"), [t("Started"), t("Mode"), t("Duration"), t("Status"), t("SNR dB"), t("Lost audio %"), t("Clipped %"), t("Turns"), t("Engine")], list.map((s) => h(
      "tr",
      {},
      h("td", {}, fmtDate(s.started_at)),
      h("td", {}, t(s.mode)),
      h("td", {}, t("{n} s", { n: s.audio_seconds.toFixed(1) })),
      h("td", {}, pill(s.status, s.status === "ended" ? true : s.status === "failed" ? false : undefined), " ", h("span", { class: "muted", dir: "auto" }, s.close_reason || "")),
      h("td", {}, String(q(s, "snr_db"))),
      h("td", {}, String(q(s, "concealed_pct"))),
      h("td", {}, String(q(s, "clipped_pct"))),
      h("td", {}, String(s.event_counts?.end_of_turn ?? 0)),
      h("td", { class: "mono" }, (s.backends || []).join(", ")),
    ))) : h("p", { class: "muted" }, t("No sessions yet."))),
  );
}

// ---- exports ---------------------------------------------------------------------------

async function download(path, filename) {
  const headers = {};
  const key = sessionStorage.getItem(KEY_STORE);
  if (key) headers.Authorization = `Bearer ${key}`;
  else headers["X-Nexora-CSRF"] = "1";
  const url = new URL(path, location.origin);
  if (state.me?.superadmin && state.org) url.searchParams.set("org_id", state.org);
  const res = await fetch(url, { headers, credentials: "same-origin" });
  if (!res.ok) throw new ApiError(res.status, t("export failed ({status})", { status: res.status }));
  const blobUrl = URL.createObjectURL(await res.blob());
  const a = h("a", { href: blobUrl, download: filename });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);
}

function exportButtons(path, name) {
  const today = new Date().toISOString().slice(0, 10);
  return h(
    "div",
    {},
    h("button", { class: "secondary", onclick: () => download(`${path}?format=csv`, `${name}-${today}.csv`) }, t("Export CSV")),
    " ",
    h("button", { class: "secondary", onclick: () => download(`${path}?format=jsonl`, `${name}-${today}.jsonl`) }, t("Export JSON Lines")),
  );
}

// ---- team (single sign-on members) -----------------------------------------------------

async function team() {
  const [members, sso] = await Promise.all([
    api("GET", "/v1/sso/members"),
    fetch("/auth/oidc/status").then((r) => r.json()).catch(() => ({ enabled: false })),
  ]);
  const email = h("input", { type: "email", placeholder: "name@company.com", "aria-label": t("Email"), dir: "ltr", autocomplete: "off" });
  const role = h("select", { "aria-label": t("Role") }, h("option", { value: "admin" }, t("admin")), h("option", { value: "viewer" }, t("viewer (usage only)")));
  const err = h("p", { class: "error", role: "alert" });
  const add = async () => {
    try {
      await api("POST", "/v1/sso/members", withOrg({ email: email.value, role: role.value }));
      render();
    } catch (ex) {
      err.textContent = ex.message;
    }
  };
  return h(
    "div",
    {},
    h("h1", {}, t("Team")),
    h("p", { class: "muted" }, sso.enabled ? t("People listed here can sign in to this dashboard with your company's single sign-on.") : t("Single sign-on is not configured on this server; members are kept for when it is.")),
    h("div", { class: "card" }, h("div", { class: "row" }, email, role, h("button", { onclick: add }, t("Add"))), err),
    h("div", { class: "card" }, members.length ? table(t("Team"), [t("Email"), t("Role"), t("Added"), t("Last sign-in"), t("Actions")], members.map((m) => h(
      "tr",
      {},
      h("td", { dir: "ltr", class: "start" }, m.email),
      h("td", {}, t(m.role)),
      h("td", {}, fmtDate(m.created_at)),
      h("td", {}, m.last_login_at ? fmtDate(m.last_login_at) : h("span", { class: "muted" }, t("never"))),
      h("td", {}, h("button", { class: "danger", "aria-label": t("Remove {email}", { email: m.email }), onclick: () => removeMember(m) }, t("Remove"))),
    ))) : h("p", { class: "muted" }, t("No members yet."))),
  );
}

function removeMember(m) {
  const d = dialog(t("Remove {email}?", { email: m.email }), h("p", {}, t("They are signed out at once.")), [
    h("button", { class: "secondary", value: "cancel" }, t("Cancel")),
    h("button", { class: "danger", onclick: async (e) => { e.preventDefault(); await api("DELETE", `/v1/sso/members/${m.id}`); d.close(); render(); } }, t("Remove")),
  ]);
}

// ---- billing ---------------------------------------------------------------------------

async function billing() {
  const reports = await api("GET", "/v1/billing/reports");
  const total = reports.filter((r) => r.status === "sent").reduce((a, r) => a + r.reported_seconds, 0);
  return h(
    "div",
    {},
    h("h1", {}, t("Billing")),
    h("p", { class: "muted" }, t("Audio is reported to billing each hour, in whole seconds, when calls end.")),
    h("div", { class: "tiles" }, tile(fmtMin(total / 60), t("minutes reported (listed hours)")), tile(String(reports.filter((r) => r.status === "failed").length), t("hours waiting to retry"))),
    h("div", { class: "card" }, reports.length ? table(t("Billing"), [t("Hour (UTC)"), t("Recorded s"), t("Reported s"), t("Status"), t("Sent")], reports.map((r) => h(
      "tr",
      {},
      h("td", { dir: "ltr", class: "start" }, String(r.period_start).replace("T", " ").slice(0, 16)),
      h("td", {}, r.audio_seconds.toFixed(1)),
      h("td", {}, String(r.reported_seconds)),
      h("td", {}, pill(r.status, r.status === "sent" ? true : r.status === "failed" ? false : undefined), r.error ? h("span", { class: "muted", dir: "auto" }, ` ${r.error}`) : null),
      h("td", {}, fmtDate(r.sent_at)),
    ))) : h("p", { class: "muted" }, t("Nothing reported yet (billing is off, or no calls have ended)."))),
  );
}

// ---- audit -----------------------------------------------------------------------------

async function audit() {
  const list = await api("GET", "/v1/audit?limit=200");
  return h(
    "div",
    {},
    h("div", { class: "row" }, h("h1", {}, t("Audit log")), exportButtons("/v1/audit/export", "audit")),
    h("div", { class: "card" }, table(t("Audit log"), [t("When"), t("Who"), t("Action"), t("Details")], list.map((a) => h("tr", {}, h("td", {}, fmtDate(a.at)), h("td", { class: "mono" }, a.actor), h("td", { class: "mono" }, a.action), h("td", { class: "mono wrap" }, JSON.stringify(a.details)))))),
  );
}

// ---- organizations (super-admin) -------------------------------------------------------

async function orgs() {
  if (!state.me.superadmin) return h("p", { class: "error" }, t("Super-admin only."));
  await loadOrgs();
  return h(
    "div",
    {},
    h("div", { class: "row" }, h("h1", {}, t("Organizations")), h("button", { onclick: () => editOrg(null) }, t("New organization"))),
    h("div", { class: "card" }, table(t("Organizations"), [t("Name"), t("ID"), t("Active"), t("Concurrent"), t("Quota (min/month)"), t("Actions")], state.orgs.map((o) => h(
      "tr",
      {},
      h("td", { dir: "auto" }, o.name),
      h("td", { class: "mono" }, o.id),
      h("td", {}, pill(o.active ? "active" : "suspended", o.active)),
      h("td", {}, String(o.max_concurrent_sessions)),
      h("td", {}, o.monthly_minutes_quota ?? t("none")),
      h("td", {}, h("button", { class: "secondary", "aria-label": t("Edit {name}", { name: o.name }), onclick: () => editOrg(o) }, t("Edit")), " ", h("button", { class: "link", "aria-label": t("Open {name}", { name: o.name }), onclick: () => { state.org = o.id; $("#org-pick").value = o.id; location.hash = "#/overview"; } }, t("Open"))),
    )))),
  );
}

function editOrg(o) {
  const name = h("input", { type: "text", value: o?.name ?? "", required: true });
  const conc = h("input", { type: "number", min: 1, value: o?.max_concurrent_sessions ?? 10 });
  const quota = h("input", { type: "number", min: 0, value: o?.monthly_minutes_quota ?? "" });
  const allow = h("textarea", { dir: "ltr" }, (o?.relay_allowlist ?? []).join("\n"));
  const active = h("input", { type: "checkbox", checked: o ? o.active : true });
  const err = h("p", { class: "error", role: "alert" });
  const body = h("div", {}, h("label", {}, `${t("Name")} `, name), h("label", {}, `${t("Concurrent sessions")} `, conc), h("label", {}, `${t("Monthly minutes quota (empty: none)")} `, quota), h("label", {}, `${t("Relay allowlist, one host per line")} `, allow), o ? h("label", { class: "check" }, active, t("Active")) : null, err);
  const d = dialog(o ? t("Edit {name}", { name: o.name }) : t("New organization"), body, [
    h("button", { class: "secondary", value: "cancel" }, t("Cancel")),
    h("button", {
      onclick: async (e) => {
        e.preventDefault();
        const payload = {
          name: name.value,
          max_concurrent_sessions: Number(conc.value),
          monthly_minutes_quota: quota.value === "" ? null : Number(quota.value),
          relay_allowlist: allow.value.split("\n").map((x) => x.trim()).filter(Boolean),
        };
        try {
          if (o) await api("PATCH", `/v1/orgs/${o.id}`, { ...payload, active: active.checked });
          else {
            const res = await api("POST", "/v1/orgs", payload);
            d.close();
            showSecret(res.api_key);
            return;
          }
          d.close();
          render();
        } catch (ex) {
          err.textContent = ex.message;
        }
      },
    }, t("Save")),
  ]);
}

if (typeof document !== "undefined" && document.getElementById("main")) start();
