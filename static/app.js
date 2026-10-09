/* Salary Calculator – front-end (vanilla, offline).
   Auth, users, companies, records with edit, pagination, collapsible sidebar.
   One delegated listener set is attached once; views only swap innerHTML. */

"use strict";

/* ------------------------------------------------------------------ utils */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

function esc(v) {
  return String(v ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}
function sym() { return (S.result && S.result.currency_symbol) || "₹"; }
function fmtNum(n, decimals = 0) {
  return Number(n || 0).toLocaleString("en-IN", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}
function money(n, decimals = 0) { return sym() + fmtNum(n, decimals); }
function money2(n) {
  const v = Number(n || 0);
  return money(v, Math.abs(v - Math.round(v)) < 0.005 ? 0 : 2);
}
function initials(name) {
  return (name || "?").trim().split(/\s+/).slice(0, 2).map((w) => w[0]).join("").toUpperCase() || "?";
}

function toast(msg, kind = "") {
  const t = document.createElement("div");
  t.className = "toast " + kind;
  t.textContent = msg;
  $("#toasts").appendChild(t);
  setTimeout(() => { t.style.transition = "opacity .35s"; t.style.opacity = "0"; }, 2800);
  setTimeout(() => t.remove(), 3200);
}

async function api(method, path, body, opts = {}) {
  const req = { method, headers: { "Content-Type": "application/json" } };
  if (body !== undefined) req.body = JSON.stringify(body);
  const res = await fetch(path, req);
  const text = await res.text();
  let data = {};
  try { data = text ? JSON.parse(text) : {}; } catch (e) { throw new Error("Unexpected server response."); }
  if (res.status === 401 && !opts.raw) {
    showLogin("Your session expired. Please sign in again.");
    throw new Error("Please sign in.");
  }
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

/* ------------------------------------------------------------------ theme */
const THEME_KEY = "salarycalc-theme";
const mq = window.matchMedia("(prefers-color-scheme: dark)");

function currentThemeChoice() {
  try { return localStorage.getItem(THEME_KEY) || "system"; } catch (e) { return "system"; }
}
function applyTheme(choice) {
  const resolved = choice === "system" ? (mq.matches ? "dark" : "light") : choice;
  document.documentElement.dataset.themeChoice = choice;
  document.documentElement.dataset.theme = resolved;
  try { localStorage.setItem(THEME_KEY, choice); } catch (e) {}
  syncThemeButtons();
}
function syncThemeButtons() {
  const choice = currentThemeChoice();
  $$("#themeSwitch [data-theme-set]").forEach((b) => {
    const on = b.dataset.themeSet === choice;
    b.classList.toggle("active", on);
    b.setAttribute("aria-pressed", on ? "true" : "false");
  });
}

/* ------------------------------------------------------- searchable dropdown */
function enhanceCombos(root = document) {
  $$("select[data-combo]", root).forEach((sel) => {
    if (sel.dataset.enhanced === "1") return;
    sel.dataset.enhanced = "1";
    sel.classList.add("native-hidden");

    const wrap = document.createElement("div");
    wrap.className = "combo";
    wrap.innerHTML =
      '<button type="button" class="combo-btn" aria-haspopup="listbox">' +
      '<span class="combo-label"></span><span class="combo-caret">▾</span></button>' +
      '<div class="combo-pop"><input type="text" class="combo-search" placeholder="Search…" />' +
      '<div class="combo-list" role="listbox"></div></div>';
    sel.parentNode.insertBefore(wrap, sel.nextSibling);

    const label = wrap.querySelector(".combo-label");
    const search = wrap.querySelector(".combo-search");
    const list = wrap.querySelector(".combo-list");
    const btn = wrap.querySelector(".combo-btn");
    const options = () => Array.from(sel.options).map((o) => ({ value: o.value, text: o.textContent }));

    const syncLabel = () => {
      const cur = sel.options[sel.selectedIndex];
      label.textContent = cur ? cur.textContent : "";
      label.classList.toggle("placeholder", !sel.value);
    };
    const renderList = (filter = "") => {
      const f = filter.trim().toLowerCase();
      const items = options().filter((o) => !f || o.text.toLowerCase().includes(f));
      list.innerHTML = items.length
        ? items.map((o) => `<div class="combo-opt ${o.value === sel.value ? "sel" : ""}" data-val="${esc(o.value)}">${esc(o.text)}</div>`).join("")
        : '<div class="combo-empty">No matches</div>';
    };
    const close = () => wrap.classList.remove("open");
    const open = () => {
      closeAllCombos();
      wrap.classList.add("open");
      search.value = "";
      renderList("");
      setTimeout(() => search.focus(), 0);
    };
    const pick = (v) => {
      sel.value = v;
      syncLabel();
      sel.dispatchEvent(new Event("input", { bubbles: true }));
      sel.dispatchEvent(new Event("change", { bubbles: true }));
      close();
    };

    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      wrap.classList.contains("open") ? close() : open();
    });
    wrap.addEventListener("click", (e) => e.stopPropagation());
    search.addEventListener("input", () => renderList(search.value));
    search.addEventListener("keydown", (e) => {
      const items = Array.from(list.querySelectorAll(".combo-opt"));
      const hi = items.findIndex((el) => el.classList.contains("hi"));
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault(); e.stopPropagation();
        const next = e.key === "ArrowDown" ? Math.min(hi + 1, items.length - 1) : Math.max(hi - 1, 0);
        items.forEach((el, i) => el.classList.toggle("hi", i === next));
        if (items[next]) items[next].scrollIntoView({ block: "nearest" });
      } else if (e.key === "Enter") {
        e.preventDefault();
        const el = items[hi] || items[0];
        if (el) pick(el.dataset.val);
      } else if (e.key === "Escape") { close(); btn.focus(); }
    });
    list.addEventListener("click", (e) => {
      const o = e.target.closest(".combo-opt");
      if (o) pick(o.dataset.val);
    });
    sel.addEventListener("change", syncLabel);
    syncLabel();
  });
}
function closeAllCombos() { $$(".combo.open").forEach((c) => c.classList.remove("open")); }
function closeUserMenu() { $$(".user-pop.open").forEach((p) => p.classList.remove("open")); }
function refreshCombo(sel) {
  const wrap = sel.nextElementSibling;
  if (wrap && wrap.classList.contains("combo")) {
    wrap.remove();
    sel.classList.remove("native-hidden");
    delete sel.dataset.enhanced;
  }
  enhanceCombos(sel.parentNode);
}

/* ------------------------------------------------------------------ state */
const S = {
  view: "calculator",
  authScreen: null,
  user: null,
  isAdmin: false,
  version: "",
  masters: { countries: [], categories: [], states: [], cities: [], companies: [], min_wages: [] },
  employees: [],
  breakups: [],
  users: [],
  settingsByCountry: {},
  draft: null,
  result: null,
  editingBreakupId: null,
  masterTab: "min_wages",
  search: "",
  page: {},
  pageSize: {},
};

const DEFAULT_DRAFT = {
  country_id: null, state_id: null, city_id: null, category_id: null, company_id: null,
  name: "Manjunatha C", designation: "Accounts Executive", experience: "2 years", age: null,
  previous_ctc: 314598, increment_pct: 10, proposed_ctc: null,
  vp_pct: 0, basic_pct: 50, hra_pct: 50, pf_type: "12% on Basic",
  asset_allowance: 1499, pt: 200, income_tax: 0, label: "", company_name: "",
};

const byId = (list, id) => list.find((x) => x.id === id) || null;
const cityById = (id) => byId(S.masters.cities, id);
const stateById = (id) => byId(S.masters.states, id);
const catById = (id) => byId(S.masters.categories, id);
const countryById = (id) => byId(S.masters.countries, id);
const companyById = (id) => byId(S.masters.companies, id);

/* ================================================================== auth screens */
function showAuth(html) {
  $("#appRoot").classList.add("hidden");
  $("#authRoot").innerHTML = html;
}
function showApp() {
  $("#authRoot").innerHTML = "";
  S.authScreen = null;
  $("#appRoot").classList.remove("hidden");
}
function authShell(title, lead, body, foot = "") {
  return `<div class="auth-root"><div class="auth-card">
    <div class="logo-big">₹</div>
    <h1>${esc(title)}</h1>
    <p class="lead">${lead}</p>
    <div id="authForm">${body}</div>
    <div class="foot">${foot}</div>
  </div></div>`;
}

function showSetup() {
  S.authScreen = "setup";
  showAuth(authShell("Welcome", "Create the administrator account for this installation. You can add more users afterwards.",
    `<div class="field"><label>Full name</label><input id="suName" placeholder="e.g. Debaranjan Pegu" /></div>
     <div class="field"><label>Email</label><input id="suEmail" type="email" placeholder="you@company.com" /></div>
     <div class="field"><label>Username</label><input id="suUser" placeholder="admin" /></div>
     <div class="row">
       <div class="field"><label>Password</label><input id="suPass" type="password" placeholder="min 8 chars, 1 number" /></div>
       <div class="field"><label>Confirm password</label><input id="suPass2" type="password" /></div>
     </div>
     <div class="notice info"><span class="glyph">🔐</span><div>Passwords are stored hashed (PBKDF2). This is a local app — keep the machine itself secure.</div></div>
     <button class="btn primary" data-auth="setup">Create administrator</button>`,
    ""));
}

function showLogin(message = "") {
  S.authScreen = "login";
  S.user = null;
  showAuth(authShell("Sign in", "Enter your username or email to continue.",
    `${message ? `<div class="notice warn"><span class="glyph">⚠️</span><div>${esc(message)}</div></div>` : ""}
     <div class="field"><label>Email or username</label><input id="liId" autocomplete="username" /></div>
     <div class="field"><label>Password</label><input id="liPass" type="password" autocomplete="current-password" /></div>
     <button class="btn primary" data-auth="login">Sign in</button>`,
    `<button class="link-btn" data-auth="show-recover">Forgot your password?</button>`));
  const pass = $("#liPass");
  if (pass) pass.addEventListener("keydown", (e) => { if (e.key === "Enter") onViewClick({ target: { closest: () => null }, __auth: "login" }); });
}

function showRecover() {
  S.authScreen = "recover";
  showAuth(authShell("Recover access", "Use the one-time recovery code you saved when the app was set up. If you have lost it, run <b>python3 app.py --reset-admin</b> on the machine hosting the app.",
    `<div class="field"><label>Administrator email</label><input id="rcEmail" type="email" /></div>
     <div class="field"><label>Recovery code</label><input id="rcCode" placeholder="XXXX-XXXX-XXXX-XXXX" /></div>
     <div class="row">
       <div class="field"><label>New password</label><input id="rcPass" type="password" /></div>
       <div class="field"><label>Confirm</label><input id="rcPass2" type="password" /></div>
     </div>
     <button class="btn primary" data-auth="recover">Reset password</button>`,
    `<button class="link-btn" data-auth="show-login">Back to sign in</button>`));
}

function showRecoveryCode(code, backTo) {
  S.authScreen = "recovery-code";
  showAuth(authShell("Save this recovery code", "This is shown only once. Keep it somewhere safe — it is the only way to recover the administrator account if the password is lost.",
    `<div class="recov-box" id="rcBox">${esc(code)}</div>
     <div class="row" style="gap:10px">
       <button class="btn" data-auth="copy-code">Copy</button>
       <button class="btn primary" data-auth="${backTo}">I have saved it</button>
     </div>`));
}

function showChangePassword(forced) {
  S.authScreen = "change-password";
  showAuth(authShell(forced ? "Set a new password" : "Change password",
    forced ? "Your password was reset by an administrator. Please choose a new one." : "Choose a new password for your account.",
    `<div class="field"><label>Current password</label><input id="cpCur" type="password" /></div>
     <div class="row">
       <div class="field"><label>New password</label><input id="cpNew" type="password" /></div>
       <div class="field"><label>Confirm</label><input id="cpNew2" type="password" /></div>
     </div>
     <button class="btn primary" data-auth="change-password">Save password</button>`,
    forced ? "" : `<button class="link-btn" data-auth="cancel-change">Cancel</button>`));
}

async function doSetup() {
  const password = $("#suPass").value;
  if (password !== $("#suPass2").value) return toast("Passwords do not match.", "bad");
  const res = await api("POST", "/api/auth/setup", {
    email: $("#suEmail").value.trim(), username: $("#suUser").value.trim(),
    display_name: $("#suName").value.trim(), password,
  }, { raw: true });
  S.user = res.user; S.version = res.version || S.version;
  showRecoveryCode(res.recovery_code, "enter-app");
}

async function doLogin() {
  const res = await api("POST", "/api/auth/login",
    { identifier: $("#liId").value.trim(), password: $("#liPass").value }, { raw: true });
  S.user = res.user;
  if (res.user.must_change_password) { showChangePassword(true); S.authScreen = "change-password"; return; }
  await enterApp();
}

async function doRecover() {
  const newPassword = $("#rcPass").value;
  if (newPassword !== $("#rcPass2").value) return toast("Passwords do not match.", "bad");
  const res = await api("POST", "/api/auth/recover", {
    email: $("#rcEmail").value.trim(),
    recovery_code: $("#rcCode").value.trim(),
    new_password: newPassword,
  }, { raw: true });
  showRecoveryCode(res.recovery_code, "show-login");
  toast("Password reset. Sign in with the new password.", "good");
}

async function doChangePassword(forced) {
  const newPassword = $("#cpNew").value;
  if (newPassword !== $("#cpNew2").value) return toast("Passwords do not match.", "bad");
  await api("POST", "/api/auth/change-password",
    { current_password: $("#cpCur").value, new_password: newPassword });
  toast("Password updated.", "good");
  if (forced) { S.user.must_change_password = 0; await enterApp(); }
  else { showApp(); render(); }
}

/* ================================================================== boot */
async function boot() {
  let status;
  try {
    status = await api("GET", "/api/auth/status", undefined, { raw: true });
  } catch (e) {
    toast("Cannot reach the app server: " + e.message, "bad");
    return;
  }
  S.version = status.version || "";
  updateVersionLabel();
  if (!status.initialized) return showSetup();
  if (!status.authenticated) return showLogin();
  S.user = status.user;
  await enterApp();
}

function updateVersionLabel() {
  const el = $("#appVersion");
  if (el) el.textContent = S.version ? "v" + S.version : "";
}

async function enterApp() {
  try {
    applyBootstrap(await api("GET", "/api/bootstrap"));
  } catch (e) {
    if (e.message !== "Please sign in.") toast(e.message, "bad");
    return;
  }
  showApp();
  updateVersionLabel();
  if (!S.draft) S.draft = sampleDraft();
  $$(".admin-only").forEach((el) => el.classList.toggle("hidden", !S.isAdmin));
  renderUserChip();
  const initial = location.hash.slice(1);
  if (VIEWS.includes(initial) && (!isAdminOnlyView(initial) || S.isAdmin)) S.view = initial;
  else S.view = "calculator";
  $$(".nav-item").forEach((n) => n.classList.toggle("active", n.dataset.view === S.view));
  render();
}

function applyBootstrap(data) {
  S.user = data.user || S.user;
  S.isAdmin = !!data.is_admin;
  S.version = data.version || S.version;
  S.network = !!data.network;
  S.tls = !!data.tls;
  S.urls = data.urls || [];
  S.masters = {
    countries: data.countries || [], categories: data.categories || [],
    states: data.states || [], cities: data.cities || [],
    companies: (data.companies || []).filter((c) => c.is_active !== 0 || true),
    min_wages: data.min_wages || [],
  };
  S.employees = data.employees || [];
  S.breakups = data.breakups || [];
  S.users = data.users || [];
  S.settingsByCountry = data.settings_by_country || {};
}

async function refreshData() {
  applyBootstrap(await api("GET", "/api/bootstrap"));
}

function sampleDraft() {
  const d = { ...DEFAULT_DRAFT };
  d.country_id = S.masters.countries[0] ? S.masters.countries[0].id : null;
  const blr = S.masters.cities.find((c) => c.name === "Bangalore");
  if (blr) { d.city_id = blr.id; d.state_id = blr.state_id; }
  const cat = S.masters.categories.find((c) => String(c.code) === "1");
  if (cat) d.category_id = cat.id;
  const co = S.masters.companies.find((c) => c.name === "Posiflex") || S.masters.companies[0];
  if (co) { d.company_id = co.id; d.company_name = co.name; }
  return d;
}

/* ------------------------------------------------------------------ router */
const VIEWS = ["calculator", "records", "masters", "settings", "users"];
const isAdminOnlyView = (v) => v === "users";

function setView(view) {
  if (!VIEWS.includes(view)) view = "calculator";
  if (isAdminOnlyView(view) && !S.isAdmin) view = "calculator";
  S.view = view;
  if (location.hash.slice(1) !== S.view) location.hash = S.view;
  closeAllCombos();
  $$(".nav-item").forEach((n) => n.classList.toggle("active", n.dataset.view === S.view));
  render();
}

function render() {
  if (!S.draft) return;
  const titles = {
    calculator: ["Calculator", "Build a compliant salary breakup in seconds"],
    records: ["Saved Records", "Every breakup kept, ready to reopen or edit"],
    masters: ["Masters", "Countries, companies, states, cities, categories and minimum wages"],
    settings: ["Statutory Rules", "PF, ESIC, gratuity and default percentages"],
    users: ["Users & Access", "Who can sign in and what they can do"],
  };
  const [title, sub] = titles[S.view] || ["", ""];
  $("#pageTitle").textContent = title;
  $("#pageSub").textContent = sub;

  const views = { calculator: viewCalculator, records: viewRecords, masters: viewMasters, settings: viewSettings, users: viewUsers };
  const out = views[S.view]() || { html: "" };
  $("#view").innerHTML = out.html;
  $("#topActions").innerHTML = out.actions || "";
  if (out.after) out.after();
}

function renderUserChip() {
  const u = S.user || {};
  $("#userMenu").innerHTML = `
    <button class="user-chip" data-user="toggle">
      <span class="avatar">${esc(initials(u.display_name || u.username))}</span>
      <span class="who">${esc(u.display_name || u.username || "")}</span>
    </button>
    <div class="user-pop" id="userPop">
      <div class="head"><b>${esc(u.display_name || u.username || "")}</b><span>${esc(u.email || "")} · ${esc(u.role || "")}</span></div>
      <div class="row-item" data-auth="open-change">🔑 Change password</div>
      <div class="row-item" data-auth="logout">↩︎ Sign out</div>
      <div class="row-item" data-auth="about">ℹ️ About · v${esc(S.version)}</div>
    </div>`;
}

/* ================================================================== CALCULATOR */
function locationOptions(selected, list, placeholder) {
  return `<option value="">${esc(placeholder)}</option>` +
    list.map((x) => `<option value="${x.id}" ${x.id === selected ? "selected" : ""}>${esc(x.name)}</option>`).join("");
}

function viewCalculator() {
  const d = S.draft;
  const states = S.masters.states.filter((s) => s.country_id === d.country_id);
  const cities = S.masters.cities.filter((c) => c.state_id === d.state_id);
  const cats = S.masters.categories.filter((c) => c.country_id === d.country_id);
  const companies = S.masters.companies.filter((c) => c.is_active !== 0);

  const editing = S.editingBreakupId
    ? `<div class="notice info"><span class="glyph">✏️</span><div>Editing an existing record. <b>Save changes</b> updates it; use <b>Save as new</b> to duplicate.</div></div>` : "";

  const html = `
  <div class="grid-2">
    <div class="card fade-in">
      <div class="card-head"><h3>Candidate &amp; package</h3><div class="grow"></div>
        <span class="tag">live preview</span></div>
      ${editing}

      <div class="row">
        <div class="field"><label>Candidate name</label>
          <input type="text" data-field="name" data-raw="1" value="${esc(d.name)}" placeholder="Full name" /></div>
        <div class="field"><label>Company</label>
          <select data-field="company_id" data-num="1" data-combo>${locationOptions(d.company_id, companies, "Select company")}</select></div>
      </div>
      <div class="row">
        <div class="field"><label>Designation</label>
          <input type="text" data-field="designation" data-raw="1" value="${esc(d.designation)}" placeholder="Role" /></div>
        <div class="field"><label>Experience</label>
          <input type="text" data-field="experience" data-raw="1" value="${esc(d.experience)}" placeholder="e.g. 2 years" /></div>
      </div>

      <div class="row-3">
        <div class="field"><label>Country</label>
          <select data-loc="country" data-combo>${locationOptions(d.country_id, S.masters.countries, "Select")}</select></div>
        <div class="field"><label>State / Territory</label>
          <select data-loc="state" data-combo>${locationOptions(d.state_id, states, "Select")}</select></div>
        <div class="field"><label>City</label>
          <select data-loc="city" data-combo>${locationOptions(d.city_id, cities, "Select")}</select></div>
      </div>
      <div class="row">
        <div class="field"><label>Wage category</label>
          <select data-field="category_id" data-num="1" data-combo>${locationOptions(d.category_id, cats, "—")}</select></div>
        <div class="field"><label>Age</label>
          <input type="number" data-field="age" value="${d.age ?? ""}" placeholder="optional" /></div>
      </div>

      <div class="divider"></div>

      <div class="row">
        <div class="field"><label>Previous CTC (annual)</label>
          <input type="number" data-field="previous_ctc" value="${d.previous_ctc ?? ""}" /></div>
        <div class="field"><label>Increment %</label>
          <input type="number" step="0.1" data-field="increment_pct" value="${d.increment_pct ?? ""}" /></div>
      </div>
      <div class="row">
        <div class="field"><label>Variable pay %</label>
          <input type="number" step="0.1" data-field="vp_pct" value="${d.vp_pct ?? ""}" /></div>
        <div class="field"><label>Basic as % of CTC</label>
          <input type="number" step="1" data-field="basic_pct" value="${d.basic_pct ?? ""}" /></div>
      </div>
      <div class="row">
        <div class="field"><label>HRA as % of Basic</label>
          <input type="number" step="1" data-field="hra_pct" value="${d.hra_pct ?? ""}" /></div>
        <div class="field"><label>PF scheme</label>
          <div class="seg" data-seg="pf_type">
            <button data-val="12% on Basic" class="${d.pf_type === "12% on Basic" ? "active" : ""}">12% on Basic</button>
            <button data-val="12% Cap" class="${d.pf_type === "12% Cap" ? "active" : ""}">12% Cap</button>
          </div></div>
      </div>
      <div class="row">
        <div class="field"><label>Asset / other allowance (monthly)</label>
          <input type="number" data-field="asset_allowance" value="${d.asset_allowance ?? ""}" /></div>
        <div class="field"><label>Professional tax (monthly)</label>
          <input type="number" data-field="pt" value="${d.pt ?? ""}" /></div>
      </div>

      <div class="btn-row" style="margin-top:6px">
        <button class="btn primary" data-act="save">${S.editingBreakupId ? "💾 Save changes" : "💾 Save record"}</button>
        ${S.editingBreakupId ? '<button class="btn" data-act="save-as-new">＋ Save as new</button><button class="btn ghost" data-act="cancel-edit">Cancel edit</button>'
      : '<button class="btn" data-act="sample">↺ Load sample</button><button class="btn ghost" data-act="clear">Clear form</button>'}
      </div>
    </div>

    <div id="resultsPanel"></div>
  </div>`;

  return {
    html,
    actions: `<button class="btn sm" data-act="print">🖨️ Print</button>
              <button class="btn sm primary" data-act="excel">⬇️ Download Excel</button>`,
    after: () => {
      enhanceCombos($("#view"));
      const panel = $("#resultsPanel");
      if (panel) {
        panel.innerHTML = resultsSkeleton();
        if (S.result) patchResults(S.result);
      }
      recompute();
    },
  };
}

function calcPayload() {
  const d = S.draft;
  return {
    country_id: d.country_id, state_id: d.state_id, city_id: d.city_id, category_id: d.category_id,
    previous_ctc: d.previous_ctc, increment_pct: d.increment_pct, proposed_ctc: d.proposed_ctc,
    vp_pct: d.vp_pct, basic_pct: d.basic_pct, hra_pct: d.hra_pct, pf_type: d.pf_type,
    asset_allowance: d.asset_allowance, pt: d.pt, income_tax: d.income_tax, label: d.label,
  };
}

let recalcToken = 0;
async function recompute() {
  const token = ++recalcToken;
  try {
    const result = await api("POST", "/api/calc", calcPayload());
    if (token !== recalcToken) return;
    S.result = result;
    patchResults(result);
  } catch (err) {
    if (token === recalcToken && err.message !== "Please sign in.") toast("Calculation failed: " + err.message, "bad");
  }
}

const COMP_SEGS = [
  { key: "basic", label: "Basic", color: "#5b8cff" },
  { key: "hra", label: "HRA", color: "#22d3ee" },
  { key: "gpa", label: "Gen. allowance", color: "#a855f7" },
  { key: "employer_pf", label: "Employer PF", color: "#34d399" },
  { key: "gratuity", label: "Gratuity", color: "#fbbf24" },
  { key: "esic_employer", label: "ESIC (er)", color: "#f97316" },
  { key: "asset_allowance", label: "Asset", color: "#64748b" },
];

function resultsSkeleton() {
  const segSpan = COMP_SEGS.map((s) => `<span data-seg="${s.key}" style="background:${s.color};width:0%"></span>`).join("");
  const legend = COMP_SEGS.map((s) =>
    `<span data-leg="${s.key}"><i style="background:${s.color}"></i><span data-legtxt="${s.key}">${esc(s.label)}</span></span>`).join("");
  const row = (label, key, extra = "") =>
    `<tr><td>${esc(label)}${extra}</td><td class="num" data-v="${key}_m"></td><td class="num" data-v="${key}_a"></td></tr>`;
  const total = (label, key) =>
    `<tr class="total-row"><td>${esc(label)}</td><td class="num" data-v="${key}_m"></td><td class="num" data-v="${key}_a"></td></tr>`;

  return `
  <div class="card">
    <div class="kpis">
      <div class="kpi accent"><div class="k-label">CTC offered / year</div>
        <div class="k-value" data-v="proposed_ctc">—</div><div class="k-sub" data-v="ctc_monthly"></div></div>
      <div class="kpi"><div class="k-label">Basic / month</div>
        <div class="k-value" data-v="basic">—</div><div class="k-sub" data-v="floor_badge"></div></div>
      <div class="kpi good"><div class="k-label">Take home / month</div>
        <div class="k-value" data-v="take_home">—</div><div class="k-sub">in hand after deductions</div></div>
      <div class="kpi" data-kpi="mw"><div class="k-label">Minimum wage</div>
        <div class="k-value" data-v="min_wage">—</div><div class="k-sub" data-v="feasibility"></div></div>
    </div>
    <div style="margin-top:16px">
      <div class="inline" style="justify-content:space-between">
        <span class="small muted">Monthly cost composition</span>
        <span class="small muted">CTC variance: <b data-v="variance"></b></span>
      </div>
      <div class="comp-bar">${segSpan}</div>
      <div class="legend">${legend}</div>
    </div>
    <div data-v="notices" style="margin-top:16px"></div>
    <div class="card-head" style="margin-top:20px"><h3>Breakup</h3><div class="grow"></div>
      <span class="tag">monthly · annual</span></div>
    <div class="table-wrap">
      <table>
        <thead><tr><th>Component</th><th class="num">Per month</th><th class="num">Per annum</th></tr></thead>
        <tbody>
          <tr class="group-row"><td colspan="3">Earnings (cash)</td></tr>
          ${row("Basic", "basic")}
          ${row("HRA", "hra")}
          ${row("General Purpose Allowance", "gpa", ' <span class="muted small">· balancing component</span>')}
          ${total("Gross cash", "cash")}
          <tr class="group-row"><td colspan="3">Deductions (employee)</td></tr>
          ${row("PF – Employee", "pf_emp")}
          ${row("Professional Tax", "pt")}
          ${row("ESIC – Employee", "esic_ee")}
          ${row("Income Tax", "tax")}
          ${total("Total deductions", "ded")}
          <tr class="group-row"><td colspan="3">Employer contributions</td></tr>
          ${row("Employer PF", "epf")}
          ${row("Gratuity", "grat")}
          ${row("ESIC – Employer", "esic_er")}
          ${row("Asset / Other Allowance", "asset")}
          ${total("Total employer cost", "er")}
          ${total("CTC (without variable pay)", "ctcwo")}
          ${total("CTC (with variable pay)", "ctcw")}
          ${total("Take home", "th")}
        </tbody>
      </table>
    </div>
  </div>`;
}

function patchResults(r) {
  const p = $("#resultsPanel");
  if (!p) return;
  const symbol = r.currency_symbol || "₹";
  const num = (x, dec) => symbol + fmtNum(x, dec || 0);
  const comp = (x) => (Math.abs(Number(x || 0)) < 0.5 ? "–" : num(x, 0));
  const set = (key, text) => {
    const el = p.querySelector(`[data-v="${key}"]`);
    if (el && el.textContent !== String(text)) el.textContent = text;
  };
  const setHtml = (key, html) => {
    const el = p.querySelector(`[data-v="${key}"]`);
    if (el && el.__html !== html) { el.innerHTML = html; el.__html = html; }
  };

  set("proposed_ctc", num(r.proposed_ctc));
  set("ctc_monthly", num(r.ctc_monthly) + " / month");
  set("basic", num(r.basic));
  set("take_home", num(r.take_home));
  set("min_wage", r.min_wage > 0 ? num(r.min_wage) : "—");
  set("feasibility", r.feasible ? "CTC balanced ✓" : "CTC must rise");
  set("variance", (r.ctc_variance > 0 ? "+" : "") + num(r.ctc_variance));
  setHtml("floor_badge", r.min_wage > 0
    ? (r.min_wage_applied
      ? '<span class="badge warn">⚖️ Govt floor applied</span>'
      : `<span class="badge good">✓ Above floor ${num(r.min_wage)}</span>`)
    : '<span class="badge ghost">No floor defined</span>');
  const mwKpi = p.querySelector('[data-kpi="mw"]');
  if (mwKpi) mwKpi.classList.toggle("bad", r.min_wage > 0 && !r.feasible);

  const vals = {};
  let total = 0;
  COMP_SEGS.forEach((s) => { const v = Math.max(0, Number(r[s.key] || 0)); vals[s.key] = v; total += v; });
  total = total || 1;
  COMP_SEGS.forEach((s) => {
    const span = p.querySelector(`[data-seg="${s.key}"]`);
    if (span) span.style.width = (vals[s.key] / total * 100).toFixed(2) + "%";
    const leg = p.querySelector(`[data-leg="${s.key}"]`);
    const txt = p.querySelector(`[data-legtxt="${s.key}"]`);
    if (txt) txt.textContent = `${s.label} · ${num(vals[s.key])}`;
    if (leg) leg.style.display = vals[s.key] > 0 ? "" : "none";
  });

  setHtml("notices", (r.warnings || []).map((w) => {
    const kind = /cannot be honoured/.test(w) ? "bad" : /No minimum wage/.test(w) ? "info" : "warn";
    const glyph = kind === "bad" ? "⛔" : kind === "info" ? "ℹ️" : "⚠️";
    return `<div class="notice ${kind}"><span class="glyph">${glyph}</span><div>${esc(w)}</div></div>`;
  }).join(""));

  const er = r.employer_pf + r.gratuity + r.esic_employer + r.asset_allowance;
  const cells = {
    basic: [comp(r.basic), comp(r.basic * 12)],
    hra: [comp(r.hra), comp(r.hra * 12)],
    gpa: [comp(r.gpa), comp(r.gpa * 12)],
    cash: [num(r.cash), num(r.cash * 12)],
    pf_emp: [comp(r.employee_pf), comp(r.employee_pf * 12)],
    pt: [comp(r.professional_tax), comp(r.professional_tax * 12)],
    esic_ee: [comp(r.esic_employee), comp(r.esic_employee * 12)],
    tax: [comp(r.income_tax), comp(r.income_tax * 12)],
    ded: [num(r.employee_deductions), num(r.employee_deductions * 12)],
    epf: [comp(r.employer_pf), comp(r.employer_pf * 12)],
    grat: [comp(r.gratuity), comp(r.gratuity * 12)],
    esic_er: [comp(r.esic_employer), comp(r.esic_employer * 12)],
    asset: [comp(r.asset_allowance), comp(r.asset_allowance * 12)],
    er: [num(er), num(er * 12)],
    ctcwo: [num(r.ctc_without_vp / 12), num(r.ctc_without_vp)],
    ctcw: [num(r.ctc_with_vp / 12), num(r.ctc_with_vp)],
    th: [num(r.take_home), num(r.take_home * 12)],
  };
  Object.keys(cells).forEach((k) => { set(k + "_m", cells[k][0]); set(k + "_a", cells[k][1]); });
}

/* ------------------------------------------------------------ save / edit */
function openSaveDialog(asNew) {
  if (!S.result) { toast("Nothing to save yet.", "bad"); return; }
  const d = S.draft;
  const companies = S.masters.companies.filter((c) => c.is_active !== 0);
  const editing = S.editingBreakupId && !asNew;
  modal({
    title: editing ? "Save changes to this record" : "Save record",
    sub: "Your name and the date/time are recorded automatically.",
    saveLabel: editing ? "Save changes" : "Save record",
    body: `
      <div class="field"><label>Candidate name</label>
        <input id="saveName" value="${esc(d.name)}" placeholder="Full name" /></div>
      <div class="field"><label>Company</label>
        <select id="saveCompany" data-combo>${locationOptions(d.company_id, companies, "Select company")}</select></div>
      <div class="field"><label>Label / note (optional)</label>
        <input id="saveLabel" value="${esc(d.label || "")}" placeholder="e.g. Offer v2" /></div>
      <div class="notice info"><span class="glyph">👤</span><div>Saved as <b>${esc(S.user.display_name || S.user.username)}</b> · ${new Date().toLocaleString()}</div></div>`,
    onSave: async (root) => {
      const name = ($("#saveName", root).value || "").trim();
      if (!name) throw new Error("Please enter the candidate name.");
      const companyId = $("#saveCompany", root).value ? Number($("#saveCompany", root).value) : null;
      const label = $("#saveLabel", root).value.trim();
      S.draft.name = name;
      S.draft.company_id = companyId;
      S.draft.company_name = (companyById(companyId) || {}).name || "";
      S.draft.label = label;

      const employee = await api("POST", "/api/employees", {
        name, country_id: d.country_id, state_id: d.state_id, city_id: d.city_id,
        company_id: companyId, designation: d.designation, experience: d.experience, age: d.age,
      });
      const payload = {
        employee_id: employee.id, label: label || name,
        inputs: { ...S.draft, city_name: (cityById(d.city_id) || {}).name, company_name: S.draft.company_name },
        result: S.result,
      };
      if (editing) payload.breakup_id = S.editingBreakupId;
      await api("POST", "/api/breakups", payload);
      await refreshData();
      toast(editing ? "Record updated ✓" : "Record saved ✓", "good");
      render();
    },
  });
  enhanceCombos($("#modalBody"));
}

function loadRecord(rec) {
  S.draft = { ...DEFAULT_DRAFT, ...rec.inputs };
  S.result = rec.result;
  S.editingBreakupId = rec.id;
  setView("calculator");
  toast("Loaded — saving will update this record.", "good");
}

async function exportExcel() {
  if (!S.result) { toast("Nothing to export yet.", "bad"); return; }
  try {
    const res = await fetch("/api/export", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...calcPayload(), company_id: S.draft.company_id, name: S.draft.name }),
    });
    if (!res.ok) throw new Error((await res.text()) || res.statusText);
    const cd = res.headers.get("Content-Disposition") || "";
    const m = /filename="?([^"]+)"?/.exec(cd);
    const a = document.createElement("a");
    a.href = URL.createObjectURL(await res.blob());
    a.download = m ? m[1] : "salary_breakup.xlsx";
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 4000);
    toast("Excel file downloaded ✓", "good");
  } catch (e) { toast("Export failed: " + e.message, "bad"); }
}

function printResult() {
  const panel = $("#resultsPanel");
  if (!panel || !panel.querySelector("table")) { toast("Nothing to print yet.", "bad"); return; }
  const w = window.open("", "_blank");
  w.document.write(`<html><head><title>Salary breakup</title><style>
    body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;padding:32px;color:#111}
    h1{font-size:20px} table{width:100%;border-collapse:collapse;margin-top:14px;font-size:13px}
    th,td{border:1px solid #ccc;padding:8px 10px;text-align:left} th{background:#f3f4f6}
    .num{text-align:right} .group-row td{background:#eef2ff;font-weight:700}
  </style></head><body><h1>Salary Breakup — ${esc(S.draft.name || "")}</h1>${panel.querySelector("table").outerHTML}</body></html>`);
  w.document.close(); w.focus(); w.print();
}

/* ================================================================== pagination */
function pageSlice(list, key) {
  const size = S.pageSize[key] || 25;
  const total = list.length;
  const pages = Math.max(1, Math.ceil(total / size));
  let page = Math.min(Math.max(1, S.page[key] || 1), pages);
  S.page[key] = page;
  (S.pager = S.pager || {})[key] = { page, pages };
  const start = (page - 1) * size;
  return { rows: list.slice(start, start + size), page, pages, total, size, from: total ? start + 1 : 0, to: Math.min(start + size, total) };
}
function pagerHtml(key, p) {
  const opts = [10, 25, 50, 100].map((n) => `<option value="${n}" ${n === p.size ? "selected" : ""}>${n} / page</option>`).join("");
  const numbers = [];
  const win = 2;
  for (let i = 1; i <= p.pages; i++) {
    if (i === 1 || i === p.pages || Math.abs(i - p.page) <= win) numbers.push(i);
    else if (numbers[numbers.length - 1] !== "…") numbers.push("…");
  }
  const buttons = numbers.map((n) => n === "…"
    ? '<span class="page-info">…</span>'
    : `<button class="btn sm ${n === p.page ? "primary" : ""}" data-page="${n}" data-key="${key}">${n}</button>`).join("");
  return `<div class="pager">
    <span class="page-info">${p.from}–${p.to} of ${p.total}</span>
    <div class="grow"></div>
    <select data-page-size data-key="${key}">${opts}</select>
    <button class="btn sm" data-page="prev" data-key="${key}" ${p.page <= 1 ? "disabled" : ""}>‹ Prev</button>
    ${buttons}
    <button class="btn sm" data-page="next" data-key="${key}" ${p.page >= p.pages ? "disabled" : ""}>Next ›</button>
  </div>`;
}

/* ================================================================== RECORDS */
function viewRecords() {
  if (!S.breakups.length) {
    return { html: `<div class="card"><div class="empty"><div class="big">🗂️</div>
      <p>No saved records yet.</p><p class="small">Build a breakup and hit <b>Save record</b>.</p></div></div>` };
  }
  const p = pageSlice(S.breakups, "records");
  const rows = p.rows.map((b) => {
    const s = b.summary || {};
    const badge = s.feasible ? `<span class="badge good">balanced</span>` : `<span class="badge bad">floor exceeded</span>`;
    return `<tr>
      <td>${esc(b.employee_name || "—")}<div class="small muted">${esc(b.label || "")}</div></td>
      <td>${esc(b.company_name || s.company || "—")}</td>
      <td class="num">${money(s.proposed_ctc)}</td>
      <td class="num">${money(s.take_home)}</td>
      <td>${badge}</td>
      <td class="small muted">${esc(b.created_by_name || "—")}<div class="small muted">${esc((b.created_at || "").replace("T", " "))}</div></td>
      <td class="right">
        <button class="icbtn" data-edit-rec="${b.id}" title="Open and edit">✏️</button>
        <button class="icbtn" data-copy-rec="${b.id}" title="Duplicate into calculator">📄</button>
        <button class="icbtn danger" data-del="${b.id}" title="Delete">🗑️</button>
      </td></tr>`;
  }).join("");
  return {
    html: `<div class="card fade-in">
      <div class="card-head"><h3>Saved records</h3><div class="grow"></div>
        <span class="tag">${S.breakups.length} total</span></div>
      <div class="table-wrap"><table>
        <thead><tr><th>Candidate</th><th>Company</th><th class="num">CTC</th>
          <th class="num">Take home</th><th>Status</th><th>Saved by / when</th><th></th></tr></thead>
        <tbody>${rows}</tbody></table></div>
      ${pagerHtml("records", p)}</div>`,
  };
}

/* ================================================================== MASTERS */
const MASTER_DEFS = {
  min_wages: {
    label: "Minimum wages", addLabel: "Add minimum wage",
    cols: [["city", "City"], ["state", "State"], ["category", "Category"], ["amount", "Monthly wage", "num"]],
    fields: [
      { k: "country_id", label: "Country", type: "fk", src: () => S.masters.countries },
      { k: "state_id", label: "State", type: "fk", src: () => S.masters.states.filter((s) => s.country_id === (form.country_id || S.draft.country_id)) },
      { k: "city_id", label: "City", type: "fk", src: () => S.masters.cities.filter((c) => c.state_id === form.state_id) },
      { k: "category_id", label: "Category", type: "fk", src: () => S.masters.categories },
      { k: "amount", label: "Monthly minimum wage", type: "number" },
      { k: "effective_from", label: "Effective from (optional)", type: "text" },
      { k: "notes", label: "Notes", type: "text" },
    ],
  },
  companies: {
    label: "Companies", addLabel: "Add company",
    cols: [["name", "Company"], ["code", "Code"], ["is_active", "Active"]],
    fields: [
      { k: "country_id", label: "Country", type: "fk", src: () => S.masters.countries },
      { k: "name", label: "Company name", type: "text" },
      { k: "code", label: "Short code (optional)", type: "text" },
      { k: "is_active", label: "Active", type: "select", num: true,
        options: [{ value: 1, label: "Yes" }, { value: 0, label: "No" }] },
    ],
  },
  cities: {
    label: "Cities", addLabel: "Add city",
    cols: [["name", "City"], ["state", "State"], ["rank", "Rank", "num"]],
    fields: [
      { k: "state_id", label: "State", type: "fk", src: () => S.masters.states },
      { k: "name", label: "City name", type: "text" },
      { k: "rank", label: "Rank (optional)", type: "number" },
    ],
  },
  states: {
    label: "States / Territories", addLabel: "Add state",
    cols: [["name", "State"], ["country", "Country"]],
    fields: [
      { k: "country_id", label: "Country", type: "fk", src: () => S.masters.countries },
      { k: "name", label: "State name", type: "text" },
    ],
  },
  categories: {
    label: "Wage categories", addLabel: "Add category",
    cols: [["code", "Code"], ["name", "Name"], ["sort_order", "Order", "num"]],
    fields: [
      { k: "country_id", label: "Country", type: "fk", src: () => S.masters.countries },
      { k: "code", label: "Code", type: "text" },
      { k: "name", label: "Name", type: "text" },
      { k: "sort_order", label: "Sort order", type: "number" },
    ],
  },
  countries: {
    label: "Countries", addLabel: "Add country",
    cols: [["name", "Country"], ["code", "Code"], ["currency_code", "Currency"], ["currency_symbol", "Symbol"], ["locale", "Locale"]],
    fields: [
      { k: "code", label: "ISO code", type: "text" },
      { k: "name", label: "Country name", type: "text" },
      { k: "currency_code", label: "Currency code", type: "text" },
      { k: "currency_symbol", label: "Currency symbol", type: "text" },
      { k: "locale", label: "Locale", type: "text" },
    ],
  },
};

let form = {};

function viewMasters() {
  const tabs = Object.keys(MASTER_DEFS).map((k) =>
    `<div class="tab ${S.masterTab === k ? "active" : ""}" data-mtab="${k}">${esc(MASTER_DEFS[k].label)}</div>`).join("");
  const def = MASTER_DEFS[S.masterTab];
  let rows = dataFor(S.masterTab);
  if (S.search) {
    const q = S.search.toLowerCase();
    rows = rows.filter((r) => Object.values(r).join(" ").toLowerCase().includes(q));
  }
  const key = "masters:" + S.masterTab;
  const p = pageSlice(rows, key);
  const body = p.rows.map((r) => {
    const cells = def.cols.map(([k, , cls]) => `<td class="${cls || ""}">${esc(displayCell(S.masterTab, r, k))}</td>`).join("");
    return `<tr>${cells}<td class="right">
      <button class="icbtn" data-edit="${r.id}" title="Edit">✏️</button>
      <button class="icbtn danger" data-remove="${r.id}" title="Delete">🗑️</button></td></tr>`;
  }).join("");

  return {
    html: `<div class="card fade-in">
      <div class="tabs">${tabs}</div>
      <div class="toolbar">
        <input class="search" type="text" id="masterSearch" placeholder="Search ${esc(def.label.toLowerCase())}…" value="${esc(S.search)}" />
        <div class="grow"></div>
        <span class="badge ghost">${rows.length} shown</span>
        <button class="btn sm" data-act="health">🩺 Data health</button>
        ${S.isAdmin ? '<button class="btn sm" data-act="masters-export" title="Download the master data as a file">⬇️ Export</button><button class="btn sm" data-act="masters-import" title="Replace the master data from a file">⬆️ Import</button>' : ""}
        <button class="btn primary sm" data-add="1">＋ ${esc(def.addLabel)}</button>
      </div>
      <div class="table-wrap"><table>
        <thead><tr>${def.cols.map(([, label, cls]) => `<th class="${cls || ""}">${esc(label)}</th>`).join("")}<th></th></tr></thead>
        <tbody>${body || `<tr><td colspan="${def.cols.length + 1}"><div class="empty">No rows.</div></td></tr>`}</tbody>
      </table></div>
      ${pagerHtml(key, p)}
    </div>`,
    actions: `<button class="btn sm ghost" data-act="reset-seed">⟲ Reset masters to seed</button>`,
  };
}

function dataFor(tab) { return S.masters[tab] || []; }

function displayCell(tab, row, key) {
  if (key === "city") return (cityById(row.city_id) || {}).name || "—";
  if (key === "state") {
    const st = stateById(row.state_id) || (row.city_id ? stateById((cityById(row.city_id) || {}).state_id) : null);
    return st ? st.name : "—";
  }
  if (key === "country") return (countryById(row.country_id) || {}).name || "—";
  if (key === "category") return (catById(row.category_id) || {}).name || "—";
  if (key === "is_active") return row.is_active ? "Yes" : "No";
  if (key === "amount") return money(row.amount);
  return row[key] ?? "";
}

async function reloadMasters() {
  await refreshData();
}

function openMasterForm(tab, row) {
  const def = MASTER_DEFS[tab];
  form = row ? { ...row } : {};
  const body = def.fields.map((f) => {
    const val = form[f.k] ?? (f.k === "country_id" ? S.draft.country_id : (f.k === "is_active" ? 1 : ""));
    if (f.type === "fk") {
      const opts = f.src().map((o) => `<option value="${o.id}" ${o.id === val ? "selected" : ""}>${esc(o.name || o.code)}</option>`).join("");
      return `<div class="field"><label>${esc(f.label)}</label><select data-mk="${f.k}" data-combo><option value="">—</option>${opts}</select></div>`;
    }
    if (f.type === "select") {
      const opts = f.options.map((o) => `<option value="${o.value}" ${String(o.value) === String(val) ? "selected" : ""}>${esc(o.label)}</option>`).join("");
      return `<div class="field"><label>${esc(f.label)}</label><select data-mk="${f.k}" data-combo>${opts}</select></div>`;
    }
    const type = f.type === "number" ? "number" : "text";
    return `<div class="field"><label>${esc(f.label)}</label><input type="${type}" data-mk="${f.k}" value="${esc(val)}" /></div>`;
  }).join("");

  modal({
    title: row ? `Edit ${def.label}` : def.addLabel,
    sub: "Changes are written straight to salary.db",
    body: `<div data-form>${body}</div>`,
    onSave: async (root) => {
      const payload = {};
      $$("[data-mk]", root).forEach((el) => {
        const key = el.dataset.mk;
        const fld = def.fields.find((f) => f.k === key) || {};
        let v = el.value;
        if (fld.type === "number" || fld.num) v = v === "" ? null : Number(v);
        else if (el.tagName === "SELECT" && v === "") v = null;
        payload[key] = v;
      });
      if (row) await api("PUT", `/api/${tab}/${row.id}`, payload);
      else await api("POST", `/api/${tab}`, payload);
      await reloadMasters();
      render();
      toast("Saved ✓", "good");
    },
  });
  enhanceCombos($("#modalBody"));
}

async function openHealth() {
  let v;
  try { v = await api("GET", "/api/validate"); }
  catch (e) { return toast("Could not run validation: " + e.message, "bad"); }
  const s = v.summary || {};
  const stats = Object.entries({
    Countries: s.countries, States: s.states, Cities: s.cities, Companies: s.companies,
    "Cities with a minimum wage": s.cities_with_min_wage, "Cities without": s.cities_without_min_wage,
    "Minimum-wage rules": s.min_wage_rules, Users: s.users, "Saved records": s.records,
  }).map(([k, val]) => `<div class="kpi"><div class="k-label">${esc(k)}</div><div class="k-value">${fmtNum(val)}</div></div>`).join("");

  const list = (items, kind) => items.slice(0, 60).map((i) =>
    `<div class="notice ${kind}"><span class="glyph">${kind === "bad" ? "⛔" : "⚠️"}</span><div>${esc(i.message)}
      <span class="muted small">· ${esc(i.table)} #${i.id ?? "-"}</span></div></div>`).join("");

  const missing = (v.cities_without_min_wage || []);
  const missingHtml = missing.length
    ? `<div class="chips" style="margin-top:10px">${missing.slice(0, 80).map((c) => `<span class="chip">${esc(c.name)}</span>`).join("")}
        ${missing.length > 80 ? `<span class="chip">+${missing.length - 80} more</span>` : ""}</div>`
    : `<p class="small muted">Every city has a minimum wage.</p>`;

  modal({
    title: "Data health",
    sub: "A once-over of the master data before you rely on it.",
    body: `
      <div class="health-grid">${stats}</div>
      <div class="divider"></div>
      ${v.errors.length ? `<h4 style="margin:0 0 8px">Errors (${v.errors.length})</h4>${list(v.errors, "bad")}` : `<div class="notice good"><span class="glyph">✅</span><div>No data errors found.</div></div>`}
      ${v.warnings.length ? `<h4 style="margin:16px 0 8px">Warnings (${v.warnings.length})</h4>${list(v.warnings, "warn")}` : ""}
      <h4 style="margin:16px 0 8px">Cities without any minimum wage (${missing.length})</h4>
      ${missingHtml}`,
    readOnly: true,
  });
}

function exportMasters() {
  const a = document.createElement("a");
  a.href = "/api/masters/export";
  a.click();
  toast("Downloading the masters file…", "good");
}

function importMasters() {
  const input = document.createElement("input");
  input.type = "file";
  input.accept = ".json,application/json";
  input.addEventListener("change", async () => {
    const file = input.files && input.files[0];
    if (!file) return;
    const go = await confirmDialog(
      "Replace ALL master data (countries, states, cities, companies, minimum wages) with this file? Saved records and users are kept.", false);
    if (!go) return;
    try {
      const data = JSON.parse(await file.text());
      applyBootstrap(await api("POST", "/api/masters/import", data));
      S.draft = sampleDraft(); S.result = null; S.editingBreakupId = null;
      render();
      toast("Masters imported ✓", "good");
    } catch (err) { toast("Import failed: " + err.message, "bad"); }
  });
  input.click();
}

/* ================================================================== USERS */
function viewUsers() {
  const key = "users";
  const p = pageSlice(S.users, key);
  const rows = p.rows.map((u) => {
    const me = S.user && u.id === S.user.id;
    return `<tr>
      <td>${esc(u.display_name || u.username)}${me ? ' <span class="badge info">you</span>' : ""}</td>
      <td>${esc(u.username)}</td>
      <td>${esc(u.email)}</td>
      <td><span class="badge ${u.role === "admin" ? "info" : "ghost"}">${esc(u.role)}</span></td>
      <td>${u.is_active ? '<span class="badge good">active</span>' : '<span class="badge bad">disabled</span>'}${u.must_change_password ? ' <span class="badge warn">must change</span>' : ""}</td>
      <td class="small muted">${esc((u.last_login_at || "never").replace("T", " "))}</td>
      <td class="right">
        <button class="icbtn" data-user-edit="${u.id}" title="Edit">✏️</button>
        <button class="icbtn" data-user-reset="${u.id}" title="Reset password">🔑</button>
        <button class="icbtn danger" data-user-del="${u.id}" title="Delete">🗑️</button>
      </td></tr>`;
  }).join("");
  return {
    html: `<div class="card fade-in">
      <div class="card-head"><h3>Users &amp; access</h3><div class="grow"></div>
        <span class="tag">${S.users.length} total</span></div>
      <div class="table-wrap"><table>
        <thead><tr><th>Name</th><th>Username</th><th>Email</th><th>Role</th><th>Status</th><th>Last sign-in</th><th></th></tr></thead>
        <tbody>${rows || '<tr><td colspan="7"><div class="empty">No users.</div></td></tr>'}</tbody></table></div>
      ${pagerHtml(key, p)}
    </div>`,
    actions: `<button class="btn primary sm" data-act="add-user">＋ Add user</button>`,
  };
}

function openUserForm(user) {
  const roles = [{ value: "user", label: "User" }, { value: "admin", label: "Administrator" }];
  const roleSel = roles.map((r) => `<option value="${r.value}" ${user && user.role === r.value ? "selected" : ""}>${esc(r.label)}</option>`).join("");
  modal({
    title: user ? "Edit user" : "Add user",
    sub: user ? "Leave the password alone to keep it unchanged." : "A password is generated automatically and shown once.",
    body: `
      <div class="row">
        <div class="field"><label>Full name</label><input id="uName" value="${esc(user ? user.display_name : "")}" /></div>
        <div class="field"><label>Username</label><input id="uUser" value="${esc(user ? user.username : "")}" /></div>
      </div>
      <div class="field"><label>Email</label><input id="uEmail" type="email" value="${esc(user ? user.email : "")}" /></div>
      <div class="row">
        <div class="field"><label>Role</label><select id="uRole">${roleSel}</select></div>
        <div class="field"><label>Status</label><select id="uActive">
          <option value="1" ${!user || user.is_active ? "selected" : ""}>Active</option>
          <option value="0" ${user && !user.is_active ? "selected" : ""}>Disabled</option></select></div>
      </div>
      ${user ? "" : `<div class="notice info"><span class="glyph">🔑</span><div>A strong password will be generated and shown once.</div></div>`}`,
    onSave: async () => {
      const payload = {
        display_name: $("#uName").value.trim(), username: $("#uUser").value.trim(),
        email: $("#uEmail").value.trim(), role: $("#uRole").value, is_active: Number($("#uActive").value),
      };
      if (user) { await api("PUT", "/api/users/" + user.id, payload); await refreshData(); render(); toast("User updated ✓", "good"); }
      else {
        const res = await api("POST", "/api/users", payload);
        await refreshData(); render();
        if (res.generated_password) showPassword("User created", res.generated_password);
        else toast("User created ✓", "good");
      }
    },
  });
}

function showPassword(title, password) {
  modal({
    title, sub: "Shown once — copy it now and share it securely.",
    body: `<div class="recov-box">${esc(password)}</div>
           <div class="notice info"><span class="glyph">ℹ️</span><div>The user will be asked to set their own password at first sign-in.</div></div>`,
    readOnly: true, saveLabel: "Done",
  });
}

/* ================================================================== SETTINGS */
function viewSettings() {
  const countryId = S.draft.country_id || (S.masters.countries[0] || {}).id;
  const s = S.settingsByCountry[String(countryId)] || {};
  const numeric = [
    ["basic_pct", "Default Basic %"], ["hra_pct", "Default HRA % (of Basic)"],
    ["pf_employee_pct", "PF employee %"], ["pf_employer_pct", "PF employer %"],
    ["pf_cap_amount", "PF cap amount (12% Cap)"], ["esic_employee_pct", "ESIC employee %"],
    ["esic_employer_pct", "ESIC employer %"], ["esic_gross_ceiling", "ESIC gross ceiling"],
    ["gratuity_pct", "Gratuity %"], ["pt_default", "Professional tax default"],
    ["asset_allowance", "Default asset allowance"], ["pay_frequency", "Payouts per year"],
  ];
  const fields = numeric.map(([k, label]) =>
    `<div class="field"><label>${esc(label)}</label><input type="number" step="0.01" data-sk="${k}" value="${s[k] ?? ""}" /></div>`).join("");
  const countrySel = S.masters.countries.map((c) =>
    `<option value="${c.id}" ${c.id === countryId ? "selected" : ""}>${esc(c.name)} (${esc(c.currency_code)})</option>`).join("");
  return {
    html: `<div class="card fade-in">
      <div class="card-head"><h3>Statutory rules</h3><div class="grow"></div>
        <select id="settingsCountry" data-combo style="max-width:240px">${countrySel}</select></div>
      <p class="small muted">These values drive every calculation for the selected country.${S.isAdmin ? "" : " Only an administrator can change them."}</p>
      <div class="row-3" style="margin-top:14px">${fields}</div>
      ${S.isAdmin ? '<div class="btn-row" style="margin-top:10px"><button class="btn primary" data-act="save-settings">💾 Save rules</button></div>' : ""}
    </div>`,
    after: () => enhanceCombos($("#view")),
  };
}

/* ================================================================== overlays */
function modal({ title, sub, body, onSave, saveLabel = "Save", readOnly = false }) {
  $("#modalRoot").innerHTML = `
    <div class="overlay"><div class="modal" data-modal>
      <h3>${esc(title)}</h3><div class="m-sub">${esc(sub || "")}</div>
      <div id="modalBody">${body}</div>
      <div class="actions">
        ${readOnly ? "" : '<button class="btn ghost" data-close="1">Cancel</button>'}
        <button class="btn primary" data-save="1">${esc(saveLabel)}</button>
      </div>
    </div></div>`;
  const overlay = $(".overlay");
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay || e.target.closest("[data-close]")) { $("#modalRoot").innerHTML = ""; return; }
    if (e.target.closest("[data-save]")) {
      if (readOnly) { $("#modalRoot").innerHTML = ""; return; }
      onSave($("#modalBody"))
        .then(() => { $("#modalRoot").innerHTML = ""; })
        .catch((err) => toast(err.message, "bad"));
    }
  });
}

function confirmDialog(message, danger = true) {
  return new Promise((resolve) => {
    $("#modalRoot").innerHTML = `
      <div class="overlay"><div class="modal" style="width:min(440px,92vw)">
        <h3>Please confirm</h3><div class="m-sub">${esc(message)}</div>
        <div class="actions">
          <button class="btn ghost" data-no="1">Cancel</button>
          <button class="btn ${danger ? "danger" : "primary"}" data-yes="1">${danger ? "Delete" : "Continue"}</button>
        </div></div></div>`;
    const overlay = $(".overlay");
    const done = (v) => { $("#modalRoot").innerHTML = ""; resolve(v); };
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay || e.target.closest("[data-no]")) done(false);
      else if (e.target.closest("[data-yes]")) done(true);
    });
  });
}

/* ================================================================== wiring */
function onInput(e) {
  if (S.authScreen) return;
  if (S.view === "masters" && e.target.id === "masterSearch") {
    S.search = e.target.value;
    const pos = e.target.selectionStart;
    render();
    const s = $("#masterSearch");
    if (s) { s.focus(); s.setSelectionRange(pos, pos); }
    return;
  }
  if (S.view !== "calculator") return;
  const input = e.target.closest("[data-field]");
  if (!input) return;
  const key = input.dataset.field;
  const raw = input.dataset.raw === "1";
  let val = input.value;
  if (!raw) val = val === "" ? null : Number(val);
  S.draft[key] = val;
  if (key === "company_id") S.draft.company_name = (companyById(val) || {}).name || "";
  if (key === "previous_ctc") S.draft.proposed_ctc = null;
  recompute();
}

function onSelectChange(e) {
  if (S.view === "calculator") {
    const sel = e.target.closest("[data-loc]");
    if (!sel) return;
    const which = sel.dataset.loc;
    const val = sel.value ? Number(sel.value) : null;
    if (which === "country") {
      S.draft.country_id = val; S.draft.state_id = null; S.draft.city_id = null;
      const cats = S.masters.categories.filter((c) => c.country_id === val);
      S.draft.category_id = cats.length ? cats[0].id : null;
      render();
    } else if (which === "state") {
      S.draft.state_id = val; S.draft.city_id = null; render();
    } else if (which === "city") {
      S.draft.city_id = val;
      const city = cityById(val);
      if (city) {
        S.draft.state_id = city.state_id;
        const mw = S.masters.min_wages.find((m) => m.city_id === val && m.category_id);
        if (mw) S.draft.category_id = mw.category_id;
      }
      render();
    }
    return;
  }
  if (S.view === "settings" && e.target.id === "settingsCountry") {
    S.draft.country_id = Number(e.target.value);
    render();
    return;
  }
  const mk = e.target.closest("[data-mk]");
  if (mk) {
    form[mk.dataset.mk] = mk.value ? Number(mk.value) || mk.value : null;
    refreshFormDropdowns(mk.dataset.mk);
  }
}

function refreshFormDropdowns(changed) {
  const def = MASTER_DEFS[S.masterTab];
  if (!def) return;
  if (changed === "country_id" || changed === "state_id") {
    const stateField = def.fields.find((f) => f.k === "state_id");
    const cityField = def.fields.find((f) => f.k === "city_id");
    const stateSel = $('[data-mk="state_id"]');
    if (stateSel && stateField) {
      stateSel.innerHTML = `<option value="">—</option>` +
        stateField.src().map((o) => `<option value="${o.id}">${esc(o.name)}</option>`).join("");
      refreshCombo(stateSel);
    }
    const citySel = $('[data-mk="city_id"]');
    if (citySel && cityField) {
      citySel.innerHTML = `<option value="">—</option>` +
        cityField.src().map((o) => `<option value="${o.id}">${esc(o.name)}</option>`).join("");
      refreshCombo(citySel);
    }
  }
}

async function handleAuthAction(act) {
  try {
    switch (act) {
      case "setup": return await doSetup();
      case "login": return await doLogin();
      case "recover": return await doRecover();
      case "show-recover": return showRecover();
      case "show-login": return showLogin();
      case "copy-code": {
        const t = $("#rcBox");
        if (t) { navigator.clipboard && navigator.clipboard.writeText(t.textContent); toast("Recovery code copied.", "good"); }
        return;
      }
      case "enter-app": return await enterApp();
      case "change-password": return await doChangePassword(!$('[data-auth="cancel-change"]'));
      case "cancel-change": return showApp(), render();
      case "open-change": closeUserMenu(); return showChangePassword(false);
      case "logout": {
        closeUserMenu();
        await api("POST", "/api/auth/logout", {}, { raw: true });
        return showLogin("You have been signed out.");
      }
      case "about": {
        closeUserMenu();
        modal({
          title: "About", sub: "", readOnly: true, saveLabel: "Close",
          body: `<div class="health-grid">
            <div class="kpi"><div class="k-label">Application</div><div class="k-value" style="font-size:16px">Salary Calculator</div></div>
            <div class="kpi"><div class="k-label">Version</div><div class="k-value" style="font-size:16px">v${esc(S.version)}</div></div>
            <div class="kpi"><div class="k-label">Signed in as</div><div class="k-value" style="font-size:16px">${esc(S.user.username)}</div></div>
            <div class="kpi"><div class="k-label">Role</div><div class="k-value" style="font-size:16px">${esc(S.user.role)}</div></div>
            <div class="kpi"><div class="k-label">Sharing</div><div class="k-value" style="font-size:16px">${S.network ? (S.tls ? "Team · HTTPS" : "Team · HTTP") : "This computer"}</div></div>
          </div>
          ${S.network && S.urls && S.urls.length ? `<p class="small muted" style="margin-top:12px">Team address</p>
            <div class="recov-box" style="font-size:13px;letter-spacing:0">${esc(S.urls[0])}</div>` : ""}
          <div class="divider"></div>
          <div class="toolbar" style="margin:0">
            <button class="btn sm" id="checkUpdates">🔄 Check for updates</button>
            <span class="small muted">Installed v${esc(S.version)}</span>
          </div>
          <div id="updateResult" style="margin-top:10px"></div>
          <p class="small muted" style="margin-top:14px">To upgrade, run <b>upgrade.command</b> (macOS), <b>upgrade.bat</b> (Windows)
            or <b>./setup.sh upgrade</b> (Linux). Your data in <b>salary.db</b> is never touched.</p>`,
        });
        const btn = $("#checkUpdates");
        if (btn) {
          btn.addEventListener("click", async () => {
            const box = $("#updateResult");
            btn.disabled = true; btn.textContent = "Checking…";
            try {
              const r = await api("GET", "/api/update/check");
              if (r.error) box.innerHTML = `<div class="notice warn"><span class="glyph">⚠️</span><div>${esc(r.error)}</div></div>`;
              else if (r.update_available) box.innerHTML = `<div class="notice info"><span class="glyph">⬆️</span><div>Version <b>${esc(r.latest)}</b> is available — you are on ${esc(r.current)}.
                <a href="${esc(r.page)}" target="_blank" rel="noopener">Open the project page</a> and run the upgrade script.</div></div>`;
              else box.innerHTML = `<div class="notice good"><span class="glyph">✅</span><div>You are on the latest version (${esc(r.current)}).</div></div>`;
            } catch (err) { box.innerHTML = `<div class="notice bad"><span class="glyph">⛔</span><div>${esc(err.message)}</div></div>`; }
            btn.disabled = false; btn.textContent = "🔄 Check for updates";
          });
        }
        return;
      }
    }
  } catch (err) {
    if (err.message !== "Please sign in.") toast(err.message, "bad");
  }
}

async function onViewClick(e) {
  const authBtn = e.target.closest("[data-auth]");
  if (authBtn || (e && e.__auth)) { return handleAuthAction(authBtn ? authBtn.dataset.auth : e.__auth); }

  const themeBtn = e.target.closest("#themeSwitch [data-theme-set]");
  if (themeBtn) { applyTheme(themeBtn.dataset.themeSet); return; }

  const userBtn = e.target.closest("[data-user]");
  if (userBtn) {
    const pop = $("#userPop");
    if (pop) pop.classList.toggle("open");
    return;
  }
  const nav = e.target.closest(".nav-item");
  if (nav) { closeUserMenu(); setView(nav.dataset.view); return; }
  if (e.target.closest("[data-modal]") || e.target.closest(".overlay")) return;
  if (e.target.closest(".user-pop")) return;
  closeAllCombos();
  closeUserMenu();

  const toggle = e.target.closest("#sidebarToggle");
  if (toggle) {
    const app = $("#appRoot");
    app.classList.toggle("collapsed");
    try { localStorage.setItem("salarycalc-sidebar", app.classList.contains("collapsed") ? "collapsed" : "open"); } catch (err) {}
    return;
  }

  if (S.view === "calculator") {
    const seg = e.target.closest("[data-seg]");
    if (seg) {
      S.draft[seg.dataset.seg] = e.target.dataset.val;
      $$("button", seg).forEach((b) => b.classList.toggle("active", b === e.target));
      recompute();
      return;
    }
  }

  // pagination
  const pg = e.target.closest("[data-page]");
  if (pg && !pg.disabled) {
    const key = pg.dataset.key;
    const info = (S.pager && S.pager[key]) || { page: 1, pages: 1 };
    const to = pg.dataset.page;
    S.page[key] = to === "prev" ? info.page - 1 : to === "next" ? info.page + 1 : Number(to);
    render();
    return;
  }

  const btn = e.target.closest("[data-act]");
  if (btn) {
    const act = btn.dataset.act;
    if (act === "save") openSaveDialog(false);
    else if (act === "save-as-new") openSaveDialog(true);
    else if (act === "cancel-edit") { S.editingBreakupId = null; S.result = null; S.draft = sampleDraft(); render(); }
    else if (act === "print") printResult();
    else if (act === "excel") exportExcel();
    else if (act === "sample") { S.draft = sampleDraft(); S.result = null; S.editingBreakupId = null; render(); }
    else if (act === "clear") { S.draft = { ...DEFAULT_DRAFT, country_id: S.draft.country_id, category_id: S.draft.category_id }; S.result = null; S.editingBreakupId = null; render(); }
    else if (act === "save-settings") await saveSettings();
    else if (act === "reset-seed") await resetSeed();
    else if (act === "health") await openHealth();
    else if (act === "masters-export") exportMasters();
    else if (act === "masters-import") importMasters();
    else if (act === "add-user") openUserForm(null);
    return;
  }

  if (S.view === "records") {
    const edit = e.target.closest("[data-edit-rec]");
    const copy = e.target.closest("[data-copy-rec]");
    const del = e.target.closest("[data-del]");
    if (edit || copy) {
      const rec = S.breakups.find((b) => b.id === Number((edit || copy).dataset[edit ? "editRec" : "copyRec"]));
      if (rec) {
        S.draft = { ...DEFAULT_DRAFT, ...rec.inputs };
        S.result = rec.result;
        S.editingBreakupId = edit ? rec.id : null;
        setView("calculator");
        toast(edit ? "Loaded — saving will update this record." : "Copied — saving creates a new record.", "good");
      }
    } else if (del) {
      if (await confirmDialog("Delete this record? This cannot be undone.")) {
        try { await api("DELETE", "/api/breakups/" + del.dataset.del); await refreshData(); render(); toast("Deleted", "good"); }
        catch (err) { toast("Delete failed: " + err.message, "bad"); }
      }
    }
    return;
  }

  if (S.view === "users") {
    const ed = e.target.closest("[data-user-edit]");
    const rs = e.target.closest("[data-user-reset]");
    const dl = e.target.closest("[data-user-del]");
    if (ed) { const u = S.users.find((x) => x.id === Number(ed.dataset.userEdit)); if (u) openUserForm(u); return; }
    if (rs) {
      const u = S.users.find((x) => x.id === Number(rs.dataset.userReset));
      if (u && await confirmDialog(`Reset the password for ${u.username}? They will be signed out and asked to set a new one.`, false)) {
        try { const res = await api("POST", `/api/users/${u.id}/reset-password`, {}); await refreshData(); render(); showPassword("Password reset", res.generated_password); }
        catch (err) { toast(err.message, "bad"); }
      }
      return;
    }
    if (dl) {
      const u = S.users.find((x) => x.id === Number(dl.dataset.userDel));
      if (u && await confirmDialog(`Delete the user ${u.username}? This cannot be undone.`)) {
        try { await api("DELETE", "/api/users/" + u.id); await refreshData(); render(); toast("User deleted", "good"); }
        catch (err) { toast(err.message, "bad"); }
      }
      return;
    }
    return;
  }

  if (S.view === "masters") {
    const tab = e.target.closest("[data-mtab]");
    if (tab) { S.masterTab = tab.dataset.mtab; S.search = ""; S.page["masters:" + tab] = 1; render(); return; }
    if (e.target.closest("[data-add]")) { openMasterForm(S.masterTab, null); return; }
    const ed = e.target.closest("[data-edit]");
    if (ed) { openMasterForm(S.masterTab, dataFor(S.masterTab).find((r) => r.id === Number(ed.dataset.edit))); return; }
    const rm = e.target.closest("[data-remove]");
    if (rm && await confirmDialog("Delete this row? Related rows may be removed too.")) {
      try { await api("DELETE", `/api/${S.masterTab}/${rm.dataset.remove}`); await reloadMasters(); render(); toast("Deleted", "good"); }
      catch (err) { toast("Delete failed: " + err.message, "bad"); }
    }
  }
}

async function saveSettings() {
  const countryId = S.draft.country_id || (S.masters.countries[0] || {}).id;
  const values = {};
  $$("[data-sk]").forEach((el) => { values[el.dataset.sk] = el.value === "" ? null : Number(el.value); });
  try {
    const res = await api("POST", "/api/settings", { country_id: countryId, values });
    S.settingsByCountry[String(countryId)] = res.settings;
    toast("Rules saved ✓", "good");
  } catch (e) { toast("Save failed: " + e.message, "bad"); }
}

async function resetSeed() {
  if (!(await confirmDialog("This replaces all master data with the seeded list and removes saved records. Users are kept. Continue?"))) return;
  try {
    applyBootstrap(await api("POST", "/api/reset"));
    S.draft = sampleDraft(); S.result = null; S.editingBreakupId = null;
    render();
    toast("Masters reset to seed ✓", "good");
  } catch (e) { toast("Reset failed: " + e.message, "bad"); }
}

document.addEventListener("DOMContentLoaded", () => {
  document.addEventListener("input", onInput);
  document.addEventListener("change", (e) => {
    const sizeSel = e.target.closest("[data-page-size]");
    if (sizeSel) { S.pageSize[sizeSel.dataset.key] = Number(sizeSel.value); S.page[sizeSel.dataset.key] = 1; render(); return; }
    onSelectChange(e);
  });
  document.addEventListener("click", onViewClick);
  syncThemeButtons();
  try {
    if (localStorage.getItem("salarycalc-sidebar") === "collapsed") $("#appRoot").classList.add("collapsed");
  } catch (e) {}
  const onSchemeChange = () => { if (currentThemeChoice() === "system") applyTheme("system"); };
  if (mq.addEventListener) mq.addEventListener("change", onSchemeChange);
  else if (mq.addListener) mq.addListener(onSchemeChange);
  window.addEventListener("hashchange", () => {
    if (!S.draft) return;
    const v = location.hash.slice(1);
    if (VIEWS.includes(v) && v !== S.view) setView(v);
  });
  boot();
});
