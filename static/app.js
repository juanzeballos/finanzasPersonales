// ============================================================
//  Gastos — PWA en JS puro (sin framework).
//  Flujo ASÍNCRONO: al cargar un gasto, el backend lo guarda como "entrada
//  pendiente" y responde al instante. Un worker lo clasifica por detrás.
//  El front SONDEA (polling) cada 2s para mostrar cuándo queda clasificado.
// ============================================================

// ---------- Constantes ----------
const TIPOS = [
  { key: "fijo", label: "Fijo", hint: "se repite cada mes" },
  { key: "necesario", label: "Necesario", hint: "indispensable pero variable" },
  { key: "prescindible", label: "Prescindible", hint: "podrías recortarlo" },
];
const MESES = ["enero","febrero","marzo","abril","mayo","junio","julio","agosto","septiembre","octubre","noviembre","diciembre"];
const THEME_KEY = "gastos-theme-v1";

// ---------- Iconos (SVG inline, estilo lucide) ----------
const P = {
  send: '<path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/>',
  trash: '<path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>',
  left: '<path d="m15 18-6-6 6-6"/>',
  right: '<path d="m9 18 6-6-6-6"/>',
  calendar: '<rect width="18" height="18" x="3" y="4" rx="2"/><path d="M3 10h18M8 2v4M16 2v4"/>',
  wallet: '<path d="M19 7V5a1 1 0 0 0-1-1H5a2 2 0 0 0 0 4h15a1 1 0 0 1 1 1v3M3 5v14a2 2 0 0 0 2 2h14a1 1 0 0 0 1-1v-3"/><path d="M18 12a2 2 0 0 0 0 4h3v-4Z"/>',
  sparkles: '<path d="M12 3l1.8 4.7L18.5 9.5 13.8 11.3 12 16l-1.8-4.7L5.5 9.5l4.7-1.8Z"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  moon: '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
  alert: '<circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>',
  lock: '<rect width="18" height="11" x="3" y="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
  loader: '<path d="M21 12a9 9 0 1 1-6.2-8.6"/>',
};
function icon(name, size = 16, cls = "") {
  return `<svg class="${cls}" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none"
    stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${P[name]}</svg>`;
}

// ---------- Helpers ----------
const pad = (n) => String(n).padStart(2, "0");
const fmt = (n) => "$" + Math.round(Number(n) || 0).toLocaleString("es-AR");
const monthKey = (fecha) => String(fecha).slice(0, 7);
function todayStr() {
  const d = new Date();
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}
const esc = (s) =>
  String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const tipoLabel = (k) => (TIPOS.find((t) => t.key === k) || TIPOS[1]).label;

// ---------- Estado ----------
const now = new Date();
const state = {
  tab: "registrar",
  dark: false,
  expenses: [],            // gastos ya clasificados (del backend)
  entradas: [],            // entradas pendientes o con error (del backend)
  cursor: { y: now.getFullYear(), m: now.getMonth() },
  vista: "control",
  draft: "",
  focusInput: false,
  error: null,             // error de conexión con el backend
  consejo: null,
  consejoLoading: false,
  open: new Set(),
  // --- autenticación ---
  usuario: null,           // null = no logueado; {id, email} = logueado
  authModo: "login",       // "login" | "registro"
  auth: { email: "", password: "" },
  authError: null,
};
let pollTimer = null;      // timer del sondeo (polling)

// Anti-parpadeo: solo re-renderizamos si los datos realmente cambiaron.
let ultimoSnapshot = "";
function snapshot() {
  return JSON.stringify({
    err: state.error,
    g: state.expenses.map((e) => [e.id, e.tipo, e.monto, e.descripcion, e.categoria, e.emoji, e.fecha]),
    e: state.entradas.map((x) => [x.id, x.estado, x.error]),
  });
}

// Animar la entrada de cada elemento UNA sola vez (no en cada refresco).
const vistos = new Set();
function popOnce(key) {
  if (vistos.has(key)) return "";
  vistos.add(key);
  return "pop";
}

// ---------- API ----------
async function api(url, opts) {
  const r = await fetch(url, opts);
  if (r.status === 204) return null;
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    const err = new Error(data.detail || "Error del servidor");
    err.status = r.status;
    throw err;
  }
  return data;
}
const cargarGastos = () => api("/gastos");
const cargarEntradas = () => api("/entradas");
const postGasto = (texto) =>
  api("/gastos", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ texto }) });
const patchTipo = (id, tipo) =>
  api(`/gastos/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ tipo }) });
const deleteGasto = (id) => api(`/gastos/${id}`, { method: "DELETE" });
const deleteEntrada = (id) => api(`/entradas/${id}`, { method: "DELETE" });
const postInforme = (mes) => api(`/informe?mes=${mes}`, { method: "POST" });
// --- autenticación ---
const getYo = () => api("/yo");
const postLogout = () => api("/logout", { method: "POST" });
const postAuth = (modo, email, password) =>
  api(`/${modo}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, password }) });

// ============================================================
//  Render
// ============================================================
function renderHeader() {
  document.getElementById("header").innerHTML = `
    <div class="wrap">
      <div class="brand">
        <span class="logo">${icon("wallet", 16)}</span>
        <span>Gastos</span>
      </div>
      <div class="header-actions">
        <button class="pill" data-action="theme" title="Cambiar tema">
          ${icon(state.dark ? "sun" : "moon", 15)}<span>${state.dark ? "Claro" : "Oscuro"}</span>
        </button>
        <div class="tabs">
          <button class="tab ${state.tab === "registrar" ? "active" : ""}" data-action="tab" data-tab="registrar">Registrar</button>
          <button class="tab ${state.tab === "mes" ? "active" : ""}" data-action="tab" data-tab="mes">El mes</button>
        </div>
        <button class="pill" data-action="logout" title="Cerrar sesión">Salir</button>
      </div>
    </div>`;
}

// --- Vista: Login / Registro (cuando no hay sesión) ---
function renderAuth() {
  const esLogin = state.authModo === "login";
  document.getElementById("header").innerHTML = "";
  document.getElementById("view").innerHTML = `
    <div class="auth-wrap">
      <div class="auth-card pop">
        <div class="auth-brand"><span class="logo">${icon("wallet", 18)}</span> Gastos</div>
        <p class="auth-title">${esLogin ? "Entrar" : "Crear cuenta"}</p>
        <input id="auth-email" type="email" autocomplete="username" placeholder="Email" value="${esc(state.auth.email)}" />
        <input id="auth-password" type="password" autocomplete="${esLogin ? "current-password" : "new-password"}" placeholder="Contraseña" value="${esc(state.auth.password)}" />
        ${state.authError ? `<div class="auth-error">${icon("alert", 14)} ${esc(state.authError)}</div>` : ""}
        <button class="auth-btn" data-action="auth-submit">${esLogin ? "Entrar" : "Crear cuenta"}</button>
        <p class="auth-toggle">
          ${esLogin ? "¿No tenés cuenta?" : "¿Ya tenés cuenta?"}
          <a data-action="auth-toggle">${esLogin ? "Crear una" : "Entrar"}</a>
        </p>
      </div>
    </div>`;
  const input = document.getElementById("auth-email");
  if (input && !state.auth.email) input.focus();
}

function cardHTML(e) {
  const abierto = state.open.has(e.id);
  const pills = TIPOS.map((t) => {
    const activo = e.tipo === t.key;
    return `<button class="type-pill t-${t.key} ${activo ? "active" : ""}" data-action="set-type" data-id="${e.id}" data-tipo="${t.key}">${t.label}</button>`;
  }).join("");
  return `
    <div class="card ${popOnce("g" + e.id)}">
      <button class="card-head" data-action="toggle" data-id="${e.id}">
        <span class="card-emoji">${esc(e.emoji || "💸")}</span>
        <div class="card-main">
          <div class="card-desc">${esc(e.descripcion)}</div>
          <div class="card-meta">
            <span class="card-cat">${esc(e.categoria)}</span>
            <span class="dot-sep"></span>
            <span class="card-tipo t-${e.tipo}"><span class="dot"></span>${tipoLabel(e.tipo)}</span>
          </div>
        </div>
        <span class="card-amount num">${fmt(e.monto)}</span>
      </button>
      ${abierto ? `
      <div class="card-foot">
        <div class="type-pills">${pills}</div>
        <button class="icon-btn" data-action="del" data-id="${e.id}" title="Eliminar">${icon("trash", 15)}</button>
      </div>` : ""}
    </div>`;
}

// --- Vista: Registrar (chat) ---
function renderRegistrar() {
  const hoy = state.expenses
    .filter((e) => e.fecha === todayStr())
    .sort((a, b) => a.id - b.id);
  const totalHoy = hoy.reduce((s, e) => s + e.monto, 0);

  const pendientes = state.entradas.filter((e) => e.estado === "pendiente");
  const errores = state.entradas.filter((e) => e.estado === "error");

  const vacio = hoy.length === 0 && state.entradas.length === 0 && !state.error;

  const chat = vacio
    ? `<div class="empty">
         <div class="badge">${icon("sparkles", 20)}</div>
         <p class="title">Contame tu primer gasto del día</p>
         <p class="sub">Escribilo como te salga: <b>"1800 de café"</b> o <b>"pagué 8 mil de luz y 3200 el delivery"</b>.</p>
       </div>`
    : [
        ...hoy.map(cardHTML),
        // entradas pendientes: burbuja "clasificando…"
        ...pendientes.map((p) => `<div class="bubble-row ${popOnce("e" + p.id)}">
               <div class="bubble">${esc(p.texto)}</div>
               <div class="thinking">${icon("loader", 14, "spin")} clasificando…</div>
             </div>`),
        // entradas con error: aviso con botón para descartar
        ...errores.map((p) => `<div class="aviso error ${popOnce("err" + p.id)}">${icon("alert", 15)}
               <span><b>"${esc(p.texto)}"</b> — ${esc(p.error || "no se pudo clasificar")}</span>
               <button class="icon-btn" data-action="del-entrada" data-id="${p.id}" title="Descartar">${icon("trash", 14)}</button>
             </div>`),
        state.error ? `<div class="aviso error pop">${icon("alert", 15)}<span>${esc(state.error)}</span></div>` : "",
      ].join("");

  return `
    <div class="scroll" id="scroll">${chat}</div>
    <div class="composer">
      ${hoy.length > 0 ? `<div class="total-line"><span class="lbl">Hoy llevás</span><span class="num" style="font-weight:600">${fmt(totalHoy)}</span></div>` : ""}
      <div class="row">
        <input id="composer-input" placeholder="Anotá un gasto…" autocomplete="off" value="${esc(state.draft)}" />
        <button class="send-btn" data-action="send">${icon("send", 17)}</button>
      </div>
    </div>`;
}

// --- Vista: El mes ---
function renderMes() {
  const key = `${state.cursor.y}-${pad(state.cursor.m + 1)}`;
  const delMes = state.expenses.filter((e) => monthKey(e.fecha) === key).sort((a, b) => b.id - a.id);
  const total = delMes.reduce((s, e) => s + e.monto, 0);

  const porTipo = TIPOS.map((t) => {
    const monto = delMes.filter((e) => e.tipo === t.key).reduce((s, e) => s + e.monto, 0);
    return { ...t, monto, pct: total ? (monto / total) * 100 : 0 };
  });
  const prescindible = porTipo.find((t) => t.key === "prescindible");

  const porCategoria = Object.values(
    delMes.reduce((acc, e) => {
      acc[e.categoria] = acc[e.categoria] || { categoria: e.categoria, monto: 0, emoji: e.emoji };
      acc[e.categoria].monto += e.monto;
      return acc;
    }, {})
  ).sort((a, b) => b.monto - a.monto);

  const nav = `
    <div class="month-nav">
      <button class="nav-btn" data-action="month" data-dir="-1">${icon("left", 16)}</button>
      <div class="label">${icon("calendar", 15)}<span>${MESES[state.cursor.m]} ${state.cursor.y}</span></div>
      <button class="nav-btn" data-action="month" data-dir="1">${icon("right", 16)}</button>
    </div>`;

  if (delMes.length === 0) {
    return `<div class="scroll col5">${nav}
      <div class="empty"><p class="title">Sin gastos este mes</p>
      <p class="sub">Registrá algunos desde la pestaña Registrar y van a aparecer acá.</p></div></div>`;
  }

  const stack = porTipo.filter((t) => t.pct > 0)
    .map((t) => `<div class="seg bg-${t.key}" style="width:${t.pct}%" title="${t.label} ${Math.round(t.pct)}%"></div>`).join("");

  const consejoHTML = state.consejoLoading
    ? `<div class="consejo-box muted">${icon("loader", 14, "spin")} pensando un consejo…</div>`
    : state.consejo
      ? `<div class="consejo-box">${esc(state.consejo)}</div>`
      : `<button class="pill" data-action="consejo" style="margin-top:12px">${icon("sparkles", 15)}<span>Consejo IA</span></button>`;

  const barra = (label, hint, monto, pct, colorCls) => `
    <div class="bar">
      <div class="bar-top">
        <div class="bar-left"><span class="bar-label">${label}</span>${hint ? `<span class="bar-hint">${hint}</span>` : ""}</div>
        <div class="bar-right"><span class="bar-pct">${Math.round(pct)}%</span><span class="num" style="font-weight:600">${fmt(monto)}</span></div>
      </div>
      <div class="bar-track"><div class="bar-fill ${colorCls}" style="width:${Math.max(pct, 1.5)}%"></div></div>
    </div>`;

  const bars = state.vista === "control"
    ? porTipo.map((t) => barra(t.label, t.hint, t.monto, t.pct, `bg-${t.key}`)).join("")
    : porCategoria.map((c) => barra(`${esc(c.emoji || "")} ${esc(c.categoria)}`, "", c.monto, total ? (c.monto / total) * 100 : 0, "bg-ink")).join("");

  return `
    <div class="scroll col5">
      ${nav}
      <div class="total-card">
        <div class="lbl">Total del mes</div>
        <div class="big num">${fmt(total)}</div>
        <div class="stack">${stack}</div>
        <div class="stack-legend">
          <span>${icon("lock", 11)} sin margen</span>
          <span>margen de maniobra ${icon("sparkles", 11)}</span>
        </div>
        ${prescindible.monto > 0 ? `<div class="insight"><b class="t-prescindible">${fmt(prescindible.monto)}</b> <span style="color:var(--muted)">(${Math.round(prescindible.pct)}%) fue prescindible — ahí está lo que podés recortar.</span></div>` : ""}
        ${consejoHTML}
      </div>

      <div class="seg-toggle">
        <button class="${state.vista === "control" ? "active" : ""}" data-action="vista" data-vista="control">Por control</button>
        <button class="${state.vista === "categoria" ? "active" : ""}" data-action="vista" data-vista="categoria">Por categoría</button>
      </div>
      <div class="stack-gap">${bars}</div>

      <div>
        <div class="section-title">Detalle</div>
        <div class="stack-gap">${delMes.map(cardHTML).join("")}</div>
      </div>
    </div>`;
}

function render() {
  if (!state.usuario) { renderAuth(); return; }   // sin sesión → pantalla de login
  const active = document.activeElement;
  const inputFocused = active && active.id === "composer-input";
  const caret = inputFocused ? active.selectionStart : null;

  renderHeader();
  document.getElementById("view").innerHTML =
    state.tab === "registrar" ? renderRegistrar() : renderMes();

  if (state.tab === "registrar") {
    const input = document.getElementById("composer-input");
    if (input && (inputFocused || state.focusInput)) {
      input.focus();
      const pos = caret ?? input.value.length;
      input.setSelectionRange(pos, pos);
    }
    const sc = document.getElementById("scroll");
    if (sc) sc.scrollTop = sc.scrollHeight;
  }
  state.focusInput = false;
  ultimoSnapshot = snapshot();  // dejamos registrado lo que se acaba de pintar
}

// ============================================================
//  Polling — sondeo del backend mientras haya entradas pendientes
// ============================================================
async function refrescar() {
  try {
    const [gastos, entradas] = await Promise.all([cargarGastos(), cargarEntradas()]);
    state.expenses = gastos || [];
    state.entradas = entradas || [];
    state.error = null;
  } catch (e) {
    if (e.status === 401) {                 // sesión vencida → volver al login
      if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
      state.usuario = null;
      render();
      return;
    }
    state.error = "No pude conectar con el servidor.";
  }
  // Clave anti-parpadeo: solo re-renderizar si el sondeo trajo algo distinto.
  if (snapshot() !== ultimoSnapshot) render();
  // si ya no quedan pendientes, frenamos el sondeo (lo reactivamos al cargar algo)
  if (pollTimer && !state.entradas.some((e) => e.estado === "pendiente")) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

function asegurarPolling() {
  if (!pollTimer) pollTimer = setInterval(refrescar, 2000);
}

// ============================================================
//  Acciones
// ============================================================
async function enviar() {
  const texto = (state.draft || "").trim();
  if (!texto) return;
  state.draft = "";
  state.error = null;
  state.focusInput = true;
  try {
    const entrada = await postGasto(texto);   // responde al instante (pendiente)
    state.entradas.push(entrada);
  } catch (e) {
    state.error = "No pude guardar el gasto. ¿Está el servidor corriendo?";
  }
  render();
  asegurarPolling();  // empezar a sondear para ver cuándo se clasifica
}

async function setTipo(id, tipo) {
  try {
    const upd = await patchTipo(id, tipo);
    const i = state.expenses.findIndex((e) => e.id === id);
    if (i >= 0) state.expenses[i] = upd;
  } catch (e) { /* noop */ }
  render();
}

async function borrar(id) {
  try {
    await deleteGasto(id);
    state.expenses = state.expenses.filter((e) => e.id !== id);
    state.open.delete(id);
  } catch (e) { /* noop */ }
  render();
}

async function descartarEntrada(id) {
  try {
    await deleteEntrada(id);
    state.entradas = state.entradas.filter((e) => e.id !== id);
  } catch (e) { /* noop */ }
  render();
}

async function pedirConsejo() {
  const key = `${state.cursor.y}-${pad(state.cursor.m + 1)}`;
  state.consejoLoading = true;
  render();
  try {
    const out = await postInforme(key);
    state.consejo = out.consejo;
  } catch (e) {
    state.consejo = "No pude generar el consejo. ¿Está Ollama corriendo?";
  } finally {
    state.consejoLoading = false;
    render();
  }
}

function setTheme(dark) {
  state.dark = dark;
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  try { localStorage.setItem(THEME_KEY, dark ? "dark" : "light"); } catch (e) {}
}

async function cargarDatos() {
  const [gastos, entradas] = await Promise.all([cargarGastos(), cargarEntradas()]);
  state.expenses = gastos || [];
  state.entradas = entradas || [];
}

async function submitAuth() {
  const email = (state.auth.email || "").trim();
  const password = state.auth.password || "";
  if (!email || !password) { state.authError = "Completá email y contraseña."; render(); return; }
  try {
    const u = await postAuth(state.authModo, email, password);
    state.usuario = u;
    state.auth = { email: "", password: "" };
    state.authError = null;
    vistos.clear();
    try { await cargarDatos(); } catch (e) { /* recién logueado, puede no haber datos */ }
    render();
    if (state.entradas.some((e) => e.estado === "pendiente")) asegurarPolling();
  } catch (e) {
    state.authError = e.message || "No se pudo. Reintentá.";
    render();
  }
}

async function logout() {
  try { await postLogout(); } catch (e) { /* igual cerramos del lado del cliente */ }
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  state.usuario = null;
  state.expenses = [];
  state.entradas = [];
  vistos.clear();
  render();
}

// ============================================================
//  Eventos (delegación)
// ============================================================
document.addEventListener("click", (ev) => {
  const el = ev.target.closest("[data-action]");
  if (!el) return;
  const a = el.dataset.action;
  const id = el.dataset.id ? Number(el.dataset.id) : null;

  if (a === "tab") { state.tab = el.dataset.tab; if (state.tab === "registrar") state.focusInput = true; render(); }
  else if (a === "theme") { setTheme(!state.dark); render(); }
  else if (a === "send") { enviar(); }
  else if (a === "toggle") { state.open.has(id) ? state.open.delete(id) : state.open.add(id); render(); }
  else if (a === "set-type") { setTipo(id, el.dataset.tipo); }
  else if (a === "del") { borrar(id); }
  else if (a === "del-entrada") { descartarEntrada(id); }
  else if (a === "month") {
    const d = new Date(state.cursor.y, state.cursor.m + Number(el.dataset.dir), 1);
    state.cursor = { y: d.getFullYear(), m: d.getMonth() };
    state.consejo = null;
    render();
  }
  else if (a === "vista") { state.vista = el.dataset.vista; render(); }
  else if (a === "consejo") { pedirConsejo(); }
  else if (a === "logout") { logout(); }
  else if (a === "auth-submit") { submitAuth(); }
  else if (a === "auth-toggle") {
    state.authModo = state.authModo === "login" ? "registro" : "login";
    state.authError = null;
    render();
  }
});

document.addEventListener("keydown", (ev) => {
  if (ev.target.id === "composer-input" && ev.key === "Enter" && !ev.shiftKey) {
    ev.preventDefault();
    enviar();
  }
  if ((ev.target.id === "auth-email" || ev.target.id === "auth-password") && ev.key === "Enter") {
    ev.preventDefault();
    submitAuth();
  }
});

document.addEventListener("input", (ev) => {
  if (ev.target.id === "composer-input") state.draft = ev.target.value;
  else if (ev.target.id === "auth-email") state.auth.email = ev.target.value;
  else if (ev.target.id === "auth-password") state.auth.password = ev.target.value;
});

// ============================================================
//  Init
// ============================================================
(async function init() {
  let dark = false;
  try {
    const saved = localStorage.getItem(THEME_KEY);
    if (saved) dark = saved === "dark";
    else if (window.matchMedia) dark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  } catch (e) {}
  setTheme(dark);

  // ¿Hay sesión activa? (la cookie viaja sola). Si sí, cargamos sus datos; si no, login.
  try {
    state.usuario = await getYo();
    await cargarDatos();
  } catch (e) {
    state.usuario = null;
  }
  render();
  if (state.usuario && state.entradas.some((e) => e.estado === "pendiente")) asegurarPolling();
})();

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}
