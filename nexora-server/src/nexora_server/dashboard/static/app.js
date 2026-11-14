// Nexora Voice Cloud admin dashboard (E8). No framework, no third-party code.
// Every value from the API is put on the page with textContent, never as HTML.

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
const fmtDate = (s) => (s ? new Date(s).toLocaleString() : "");
const fmtMin = (m) => (m >= 100 ? Math.round(m).toLocaleString() : m.toFixed(1));

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

async function start() {
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
    showSignin("This key does not have the admin scope.");
    return;
  }
  $("#signin").hidden = true;
  $("#nav").hidden = false;
  $("#signout").hidden = false;
  $("#who").textContent = state.me.superadmin ? "super-admin" : state.me.org_name || state.me.org_id;
  for (const el of document.querySelectorAll("[data-superadmin]")) el.hidden = !state.me.superadmin;
  if (state.me.superadmin) await loadOrgs();
  else state.org = state.me.org_id;
  if (!location.hash) location.hash = state.me.superadmin ? "#/orgs" : "#/overview";
  await render();
}

async function loadOrgs() {
  state.orgs = await api("GET", "/v1/orgs");
  const pick = $("#org-pick");
  pick.replaceChildren(
    h("option", { value: "" }, "Choose an organization"),
    ...state.orgs.map((o) => h("option", { value: o.id, selected: o.id === state.org }, o.name)),
  );
  pick.onchange = () => {
    state.org = pick.value || null;
    render();
  };
}

const VIEWS = { overview, keys, profiles, sessions, team, billing, audit, orgs };

async function render() {
  if (!state.me) return;
  const name = (location.hash.replace(/^#\//, "") || "overview").split("/")[0];
  for (const a of document.querySelectorAll("nav a")) a.classList.toggle("active", a.getAttribute("href") === `#/${name}`);
  const view = VIEWS[name] || overview;
  const root = $("#view");
  if (view !== orgs && state.me.superadmin && !state.org) {
    root.replaceChildren(h("div", { class: "card" }, h("p", {}, "Choose an organization at the top right.")));
    return;
  }
  root.replaceChildren(h("p", { class: "muted" }, "Loading..."));
  try {
    root.replaceChildren(await view());
  } catch (err) {
    root.replaceChildren(h("div", { class: "card" }, h("p", { class: "error" }, err.message)));
  }
}

function dialog(title, body, actions) {
  // a fresh <dialog> each time: a closing dialog's late "close" event can never reach the
  // next one (that once blanked a new API key before it could be copied)
  for (const old of document.querySelectorAll("dialog.closing")) old.remove();
  const d = h("dialog", { class: "modal" }, h("form", { method: "dialog" }, h("h2", {}, title), body, h("div", { class: "row" }, h("span"), h("div", {}, ...actions))));
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
  svg.setAttribute("aria-label", "Audio minutes per day");
  const max = Math.max(1, ...days.map((d) => d.audio_minutes));
  const w = 560 / Math.max(days.length, 1);
  const el = (tag, attrs, text) => {
    const e = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, String(v));
    if (text !== undefined) e.textContent = text;
    svg.append(e);
    return e;
  };
  el("line", { x1: 30, y1: 190, x2: 590, y2: 190 });
  el("text", { x: 0, y: 14 }, `${fmtMin(max)} min`);
  days.forEach((d, i) => {
    const bh = (d.audio_minutes / max) * 170;
    const rect = el("rect", { x: 32 + i * w, y: 190 - bh, width: Math.max(w - 3, 1), height: bh, rx: 2 });
    const tip = document.createElementNS(NS, "title");
    tip.textContent = `${d.date}: ${fmtMin(d.audio_minutes)} min, ${d.sessions} sessions`;
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
    h("h1", {}, org.name),
    h(
      "div",
      { class: "tiles" },
      tile(fmtMin(used), "minutes this month"),
      tile(quota ? `${Math.round(pct)}%` : "none", quota ? `of ${quota.toLocaleString()} minute quota` : "monthly quota"),
      tile(String(usage.sessions), "sessions, last 30 days"),
      tile(String(org.max_concurrent_sessions), "concurrent sessions allowed"),
    ),
    quota ? h("div", { class: "card" }, meter(pct), h("p", { class: "muted" }, `${fmtMin(used)} of ${quota} minutes used`)) : null,
    h("div", { class: "card" }, h("h2", {}, "Audio minutes per day (last 30 days)"), usage.days.length ? barChart(fillDays(usage.days, new Date(usage.period_start), new Date(usage.period_end))) : h("p", { class: "muted" }, "No sessions yet.")),
    h("div", { class: "card" }, h("h2", {}, "Relay allowlist"), org.relay_allowlist.length ? h("ul", {}, org.relay_allowlist.map((x) => h("li", { class: "mono" }, x))) : h("p", { class: "muted" }, "Empty: Relay mode is off for this organization.")),
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

function meter(pct) {
  const bar = h("span");
  bar.style.width = `${pct}%`; // CSSOM, allowed by the CSP (inline style attributes are not)
  return h("div", { class: "meter", role: "meter", "aria-valuenow": Math.round(pct), "aria-valuemin": 0, "aria-valuemax": 100 }, bar);
}

function tile(num, label) {
  return h("div", { class: "card tile" }, h("div", { class: "num" }, num), h("div", { class: "label" }, label));
}

// ---- API keys --------------------------------------------------------------------------

const SCOPES = ["stream", "admin", "usage:read"];

async function keys() {
  const list = await api("GET", "/v1/keys");
  const tbody = h("tbody", {}, list.map((k) => h(
    "tr",
    {},
    h("td", {}, k.name || h("span", { class: "muted" }, "(no name)")),
    h("td", { class: "mono" }, `${k.prefix}...`),
    h("td", {}, k.scopes.join(", ")),
    h("td", {}, fmtDate(k.created_at)),
    h("td", {}, k.last_used_at ? fmtDate(k.last_used_at) : h("span", { class: "muted" }, "never")),
    h("td", {}, k.revoked_at ? h("span", { class: "pill bad" }, "revoked") : h("button", { class: "danger", onclick: () => revokeKey(k) }, "Revoke")),
  )));
  return h(
    "div",
    {},
    h("div", { class: "row" }, h("h1", {}, "API keys"), h("button", { onclick: newKey }, "New key")),
    h("div", { class: "card" }, h("table", {}, h("thead", {}, h("tr", {}, ["Name", "Key", "Scopes", "Created", "Last used", ""].map((t) => h("th", {}, t)))), tbody)),
  );
}

function newKey() {
  const name = h("input", { type: "text", maxlength: 200, placeholder: "e.g. production agents" });
  const boxes = SCOPES.map((sc) => h("input", { type: "checkbox", value: sc, checked: sc === "stream" }));
  const err = h("p", { class: "error", role: "alert" });
  const body = h("div", {}, h("label", {}, "Name ", name), ...SCOPES.map((sc, i) => h("label", { class: "check" }, boxes[i], sc)), err);
  const d = dialog("New API key", body, [
    h("button", { class: "secondary", value: "cancel" }, "Cancel"),
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
    }, "Create"),
  ]);
}

function showSecret(secret) {
  const box = h("div", { class: "secret mono" }, secret);
  const d = dialog("Copy your new key now", h("div", {}, h("p", {}, "It will not be shown again. Store it in your secrets manager."), box), [
    h("button", { class: "secondary", onclick: (e) => { e.preventDefault(); navigator.clipboard?.writeText(secret); } }, "Copy"),
    h("button", { value: "done" }, "Done"),
  ]);
  d.addEventListener("close", () => { box.textContent = ""; render(); }, { once: true });
}

function revokeKey(k) {
  const d = dialog(`Revoke ${k.name || k.prefix}?`, h("p", {}, "Anything using this key stops working at once. This cannot be undone."), [
    h("button", { class: "secondary", value: "cancel" }, "Cancel"),
    h("button", { class: "danger", onclick: async (e) => { e.preventDefault(); await api("DELETE", `/v1/keys/${k.id}`); d.close(); render(); } }, "Revoke"),
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
      return [name, h("label", { class: "check" }, (inputs[name] = input), label, v === undefined ? h("span", { class: "muted" }, " (default)") : null)];
    }
    if (Array.isArray(type)) {
      input = h("select", {}, h("option", { value: "" }, "(default)"), type.map((o) => h("option", { value: o, selected: v === o }, o)));
    } else {
      input = h("input", { type: "number", step: "any", value: v ?? "" });
    }
    return [name, h("label", {}, label, " ", (inputs[name] = input))];
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
    h("div", { class: "row" }, h("h1", {}, "Profiles"), h("button", { onclick: () => editProfile(null) }, "New profile")),
    h("p", { class: "muted" }, "A profile is a named set of audio and turn-taking settings; clients pick one with ?profile=name."),
    h("div", { class: "card" }, list.length ? h("table", {}, h("thead", {}, h("tr", {}, ["Name", "Audio", "Turns", "Updated", ""].map((t) => h("th", {}, t)))), h("tbody", {}, list.map((p) => h(
      "tr",
      {},
      h("td", {}, p.name, p.is_default ? h("span", { class: "pill good" }, " default") : null),
      h("td", { class: "mono" }, JSON.stringify(p.audio_settings)),
      h("td", { class: "mono" }, p.turn_settings === null ? "off" : JSON.stringify(p.turn_settings)),
      h("td", {}, fmtDate(p.updated_at)),
      h("td", {}, h("button", { class: "secondary", onclick: () => editProfile(p) }, "Edit"), " ", h("button", { class: "danger", onclick: () => deleteProfile(p) }, "Delete")),
    )))) : h("p", { class: "muted" }, "No profiles yet: every session uses the built-in defaults.")),
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
    h("label", {}, "Name ", name),
    h("div", { class: "grid2" }, h("div", {}, h("h2", {}, "Audio"), audio.els, h("label", {}, "Other audio settings (JSON) ", advAudio)), h("div", {}, h("h2", {}, "Turn-taking"), h("label", { class: "check" }, noTurns, "No turn events"), turns.els, h("label", {}, "Other turn settings (JSON) ", advTurns))),
    h("label", { class: "check" }, isDefault, "Default profile"),
    err,
  );
  const d = dialog(p ? `Edit ${p.name}` : "New profile", body, [
    h("button", { class: "secondary", value: "cancel" }, "Cancel"),
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
          err.textContent = ex instanceof SyntaxError ? `Invalid JSON: ${ex.message}` : ex.message;
        }
      },
    }, "Save"),
  ]);
}

function deleteProfile(p) {
  const d = dialog(`Delete ${p.name}?`, h("p", {}, "Clients that ask for this profile will be refused."), [
    h("button", { class: "secondary", value: "cancel" }, "Cancel"),
    h("button", { class: "danger", onclick: async (e) => { e.preventDefault(); await api("DELETE", `/v1/profiles/${p.id}`); d.close(); render(); } }, "Delete"),
  ]);
}

// ---- sessions --------------------------------------------------------------------------

async function sessions() {
  const list = await api("GET", "/v1/sessions?limit=100");
  const q = (s, k) => (s.quality && s.quality[k] !== undefined && s.quality[k] !== null ? s.quality[k] : "");
  return h(
    "div",
    {},
    h("div", { class: "row" }, h("h1", {}, "Recent sessions"), exportButtons("/v1/sessions/export", "sessions")),
    h("div", { class: "card" }, list.length ? h("table", {}, h("thead", {}, h("tr", {}, ["Started", "Mode", "Duration", "Status", "SNR dB", "Lost audio %", "Clipped %", "Turns", "Engine"].map((t) => h("th", {}, t)))), h("tbody", {}, list.map((s) => h(
      "tr",
      {},
      h("td", {}, fmtDate(s.started_at)),
      h("td", {}, s.mode),
      h("td", {}, `${s.audio_seconds.toFixed(1)} s`),
      h("td", {}, h("span", { class: `pill ${s.status === "ended" ? "good" : s.status === "failed" ? "bad" : ""}` }, s.status), " ", h("span", { class: "muted" }, s.close_reason || "")),
      h("td", {}, String(q(s, "snr_db"))),
      h("td", {}, String(q(s, "concealed_pct"))),
      h("td", {}, String(q(s, "clipped_pct"))),
      h("td", {}, String(s.event_counts?.end_of_turn ?? 0)),
      h("td", { class: "mono" }, (s.backends || []).join(", ")),
    )))) : h("p", { class: "muted" }, "No sessions yet.")),
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
  if (!res.ok) throw new ApiError(res.status, `export failed (${res.status})`);
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
    h("button", { class: "secondary", onclick: () => download(`${path}?format=csv`, `${name}-${today}.csv`) }, "Export CSV"),
    " ",
    h("button", { class: "secondary", onclick: () => download(`${path}?format=jsonl`, `${name}-${today}.jsonl`) }, "Export JSON Lines"),
  );
}

// ---- team (single sign-on members) -----------------------------------------------------

async function team() {
  const [members, sso] = await Promise.all([
    api("GET", "/v1/sso/members"),
    fetch("/auth/oidc/status").then((r) => r.json()).catch(() => ({ enabled: false })),
  ]);
  const email = h("input", { type: "text", placeholder: "name@company.com", "aria-label": "Email" });
  const role = h("select", { "aria-label": "Role" }, h("option", { value: "admin" }, "admin"), h("option", { value: "viewer" }, "viewer (usage only)"));
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
    h("h1", {}, "Team"),
    h("p", { class: "muted" }, sso.enabled ? "People listed here can sign in to this dashboard with your company's single sign-on." : "Single sign-on is not configured on this server; members are kept for when it is."),
    h("div", { class: "card" }, h("div", { class: "row" }, email, role, h("button", { onclick: add }, "Add")), err),
    h("div", { class: "card" }, members.length ? h("table", {}, h("thead", {}, h("tr", {}, ["Email", "Role", "Added", "Last sign-in", ""].map((t) => h("th", {}, t)))), h("tbody", {}, members.map((m) => h(
      "tr",
      {},
      h("td", {}, m.email),
      h("td", {}, m.role),
      h("td", {}, fmtDate(m.created_at)),
      h("td", {}, m.last_login_at ? fmtDate(m.last_login_at) : h("span", { class: "muted" }, "never")),
      h("td", {}, h("button", { class: "danger", onclick: () => removeMember(m) }, "Remove")),
    )))) : h("p", { class: "muted" }, "No members yet.")),
  );
}

function removeMember(m) {
  const d = dialog(`Remove ${m.email}?`, h("p", {}, "They are signed out at once."), [
    h("button", { class: "secondary", value: "cancel" }, "Cancel"),
    h("button", { class: "danger", onclick: async (e) => { e.preventDefault(); await api("DELETE", `/v1/sso/members/${m.id}`); d.close(); render(); } }, "Remove"),
  ]);
}

// ---- billing ---------------------------------------------------------------------------

async function billing() {
  const reports = await api("GET", "/v1/billing/reports");
  const total = reports.filter((r) => r.status === "sent").reduce((a, r) => a + r.reported_seconds, 0);
  return h(
    "div",
    {},
    h("h1", {}, "Billing"),
    h("p", { class: "muted" }, "Audio is reported to billing each hour, in whole seconds, when calls end."),
    h("div", { class: "tiles" }, tile(fmtMin(total / 60), "minutes reported (listed hours)"), tile(String(reports.filter((r) => r.status === "failed").length), "hours waiting to retry")),
    h("div", { class: "card" }, reports.length ? h("table", {}, h("thead", {}, h("tr", {}, ["Hour (UTC)", "Recorded s", "Reported s", "Status", "Sent"].map((t) => h("th", {}, t)))), h("tbody", {}, reports.map((r) => h(
      "tr",
      {},
      h("td", {}, String(r.period_start).replace("T", " ").slice(0, 16)),
      h("td", {}, r.audio_seconds.toFixed(1)),
      h("td", {}, String(r.reported_seconds)),
      h("td", {}, h("span", { class: `pill ${r.status === "sent" ? "good" : "bad"}` }, r.status), r.error ? h("span", { class: "muted" }, ` ${r.error}`) : null),
      h("td", {}, fmtDate(r.sent_at)),
    )))) : h("p", { class: "muted" }, "Nothing reported yet (billing is off, or no calls have ended).")),
  );
}

// ---- audit -----------------------------------------------------------------------------

async function audit() {
  const list = await api("GET", "/v1/audit?limit=200");
  return h(
    "div",
    {},
    h("div", { class: "row" }, h("h1", {}, "Audit log"), exportButtons("/v1/audit/export", "audit")),
    h("div", { class: "card" }, h("table", {}, h("thead", {}, h("tr", {}, ["When", "Who", "Action", "Details"].map((t) => h("th", {}, t)))), h("tbody", {}, list.map((a) => h("tr", {}, h("td", {}, fmtDate(a.at)), h("td", { class: "mono" }, a.actor), h("td", {}, a.action), h("td", { class: "mono" }, JSON.stringify(a.details))))))),
  );
}

// ---- organizations (super-admin) -------------------------------------------------------

async function orgs() {
  if (!state.me.superadmin) return h("p", { class: "error" }, "Super-admin only.");
  await loadOrgs();
  return h(
    "div",
    {},
    h("div", { class: "row" }, h("h1", {}, "Organizations"), h("button", { onclick: () => editOrg(null) }, "New organization")),
    h("div", { class: "card" }, h("table", {}, h("thead", {}, h("tr", {}, ["Name", "ID", "Active", "Concurrent", "Quota (min/month)", ""].map((t) => h("th", {}, t)))), h("tbody", {}, state.orgs.map((o) => h(
      "tr",
      {},
      h("td", {}, o.name),
      h("td", { class: "mono" }, o.id),
      h("td", {}, h("span", { class: `pill ${o.active ? "good" : "bad"}` }, o.active ? "active" : "suspended")),
      h("td", {}, String(o.max_concurrent_sessions)),
      h("td", {}, o.monthly_minutes_quota ?? "none"),
      h("td", {}, h("button", { class: "secondary", onclick: () => editOrg(o) }, "Edit"), " ", h("button", { class: "link", onclick: () => { state.org = o.id; $("#org-pick").value = o.id; location.hash = "#/overview"; } }, "Open")),
    ))))),
  );
}

function editOrg(o) {
  const name = h("input", { type: "text", value: o?.name ?? "", required: true });
  const conc = h("input", { type: "number", min: 1, value: o?.max_concurrent_sessions ?? 10 });
  const quota = h("input", { type: "number", min: 0, value: o?.monthly_minutes_quota ?? "" });
  const allow = h("textarea", {}, (o?.relay_allowlist ?? []).join("\n"));
  const active = h("input", { type: "checkbox", checked: o ? o.active : true });
  const err = h("p", { class: "error", role: "alert" });
  const body = h("div", {}, h("label", {}, "Name ", name), h("label", {}, "Concurrent sessions ", conc), h("label", {}, "Monthly minutes quota (empty: none) ", quota), h("label", {}, "Relay allowlist, one host per line ", allow), o ? h("label", { class: "check" }, active, "Active") : null, err);
  const d = dialog(o ? `Edit ${o.name}` : "New organization", body, [
    h("button", { class: "secondary", value: "cancel" }, "Cancel"),
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
    }, "Save"),
  ]);
}

if (typeof document !== "undefined" && document.getElementById("main")) start();
