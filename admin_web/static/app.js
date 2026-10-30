"use strict";
const $ = (id) => document.getElementById(id);
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
let token = localStorage.getItem("hire_admin_token") || "";
let clientsCache = [];
let overviewCache = null;
let salesCache = [];
let ws = null;
let wsTimer = null;
let msgTarget = null;

async function api(path, opts = {}) {
  const res = await fetch(path, {
    ...opts,
    headers: { "Content-Type": "application/json", Authorization: "Bearer " + token, ...(opts.headers || {}) },
  });
  if (res.status === 401) {
    logout();
    throw new Error("login required");
  }
  return res;
}
const get = (p) => api(p).then((r) => r.json());
const post = (p, body) => api(p, { method: "POST", body: JSON.stringify(body || {}) }).then((r) => r.json());

function toast(html) {
  const box = $("toasts");
  const el = document.createElement("div");
  el.className = "toast";
  el.innerHTML = html;
  box.appendChild(el);
  while (box.children.length > 4) box.firstChild.remove();
  setTimeout(() => {
    el.classList.add("out");
    setTimeout(() => el.remove(), 320);
  }, 4200);
}

function animateCount(el, to, money) {
  const from = parseFloat(el.dataset.v || "0");
  el.dataset.v = to;
  if (reducedMotion || Math.abs(to - from) < 0.001) {
    el.textContent = money ? "$" + Math.round(to).toLocaleString() : Math.round(to).toLocaleString();
    return;
  }
  const t0 = performance.now();
  const dur = 700;
  function frame(t) {
    const p = Math.min(1, (t - t0) / dur);
    const eased = 1 - Math.pow(1 - p, 3);
    const v = from + (to - from) * eased;
    el.textContent = money ? "$" + Math.round(v).toLocaleString() : Math.round(v).toLocaleString();
    if (p < 1) requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
}

function bump(cardId) {
  if (reducedMotion) return;
  const el = $(cardId);
  el.classList.remove("bump");
  void el.offsetWidth;
  el.classList.add("bump");
}

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}
function shortTx(tx) {
  tx = tx || "";
  return tx.length > 14 ? tx.slice(0, 8) + "…" + tx.slice(-6) : tx;
}
function fmtDay(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return isNaN(d) ? "—" : d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

/* ---------- views ---------- */
function show(view) {
  document.querySelectorAll(".nav button").forEach((b) => b.classList.toggle("on", b.dataset.view === view));
  ["overview", "pending", "clients", "broadcast", "settings"].forEach((v) => {
    $("view-" + v).classList.toggle("hidden", v !== view);
  });
  $("view-title").textContent = view[0].toUpperCase() + view.slice(1);
  if (view === "overview") drawCharts();
}
document.querySelectorAll(".nav button").forEach((b) => b.addEventListener("click", () => show(b.dataset.view)));

/* ---------- overview ---------- */
async function loadOverview() {
  const [ov, sales, clients] = await Promise.all([get("/api/overview"), get("/api/sales?days=30"), get("/api/clients")]);
  overviewCache = ov;
  salesCache = sales;
  clientsCache = clients;
  animateCount($("stat-revenue"), ov.revenue_month, true);
  $("stat-revenue-sub").textContent = "total $" + Math.round(ov.revenue_total).toLocaleString();
  animateCount($("stat-pending"), ov.pending, false);
  animateCount($("stat-active"), ov.active, false);
  $("stat-active-sub").textContent = "of " + ov.total + " users";
  animateCount($("stat-total"), ov.total, false);
  $("stat-total-sub").textContent = ov.expired + " expired · " + ov.rejected + " rejected";
  const badge = $("pending-badge");
  badge.textContent = ov.pending;
  badge.classList.toggle("hidden", ov.pending === 0);
  const tot = sales.reduce((a, s) => a + s.revenue, 0);
  const n = sales.reduce((a, s) => a + s.sales, 0);
  $("sales-total").textContent = "$" + Math.round(tot).toLocaleString() + " · " + n + " sales in 30 days";
  renderRecent(clients.slice(0, 8));
  drawCharts();
  renderPending();
  renderClients();
}

function renderRecent(clients) {
  $("recent-list").innerHTML = clients.map((c) =>
    `<li><span class="pill ${esc(c.status)}">${esc(c.status)}</span><b>${esc("@" + (c.username || c.user_id))}</b><span class="muted">${esc(c.plan || "")} · $${esc(c.amount_usd)} · ${fmtDay(c.hired_at)}</span></li>`
  ).join("") || '<li class="muted">No users yet.</li>';
}

/* ---------- charts (dependency-free canvas) ---------- */
const ACCENT = "#c8f04b";
const GRID = "rgba(139,149,161,0.16)";
const PLAN_COLORS = { daily: "#c8f04b", weekly: "#5ec8f0", monthly: "#f0a35e" };
let chartProgress = 0;
let donutProgress = 0;

function setupCanvas(id) {
  const cv = $(id);
  const r = cv.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  cv.width = Math.max(1, r.width * dpr);
  cv.height = Math.max(1, r.height * dpr);
  const ctx = cv.getContext("2d");
  ctx.scale(dpr, dpr);
  return { ctx, w: r.width, h: r.height };
}

function drawArea(progress) {
  const { ctx, w, h } = setupCanvas("sales-chart");
  const data = salesCache;
  ctx.clearRect(0, 0, w, h);
  const padL = 46, padB = 24, padT = 10;
  const max = Math.max(10, ...data.map((d) => d.revenue));
  const X = (i) => padL + (i / Math.max(1, data.length - 1)) * (w - padL - 8);
  const Y = (v) => padT + (h - padB - padT) * (1 - v / max);
  ctx.strokeStyle = GRID;
  ctx.fillStyle = "#8b95a1";
  ctx.font = "10px ui-monospace, monospace";
  ctx.lineWidth = 1;
  for (let g = 0; g <= 4; g++) {
    const v = (max / 4) * g;
    ctx.beginPath();
    ctx.moveTo(padL, Y(v));
    ctx.lineTo(w - 4, Y(v));
    ctx.stroke();
    ctx.fillText("$" + Math.round(v), 4, Y(v) + 3);
  }
  const n = Math.max(2, Math.floor(data.length * progress));
  const pts = data.slice(0, n);
  if (pts.length < 2) return;
  ctx.beginPath();
  ctx.moveTo(X(0), Y(0));
  pts.forEach((d, i) => ctx.lineTo(X(i), Y(d.revenue)));
  ctx.lineTo(X(pts.length - 1), Y(0));
  ctx.closePath();
  ctx.fillStyle = "rgba(200,240,75,0.10)";
  ctx.fill();
  ctx.beginPath();
  pts.forEach((d, i) => (i ? ctx.lineTo(X(i), Y(d.revenue)) : ctx.moveTo(X(i), Y(d.revenue))));
  ctx.strokeStyle = ACCENT;
  ctx.lineWidth = 2;
  ctx.stroke();
  pts.forEach((d, i) => {
    if (d.sales === 0) return;
    ctx.beginPath();
    ctx.arc(X(i), Y(d.revenue), 3, 0, 7);
    ctx.fillStyle = ACCENT;
    ctx.fill();
  });
  const step = Math.ceil(data.length / 6);
  ctx.fillStyle = "#8b95a1";
  for (let i = 0; i < pts.length; i += step) {
    ctx.fillText(data[i].date.slice(5), X(i) - 12, h - 8);
  }
  drawArea._geom = { X, Y, padL, w };
}

$("sales-chart").addEventListener("mousemove", (ev) => {
  const g = drawArea._geom;
  if (!g || !salesCache.length) return;
  const r = ev.target.getBoundingClientRect();
  const x = ev.clientX - r.left;
  let best = 0, bd = 1e9;
  salesCache.forEach((d, i) => {
    const dx = Math.abs(g.X(i) - x);
    if (dx < bd) { bd = dx; best = i; }
  });
  const d = salesCache[best];
  ev.target.title = `${d.date} · $${d.revenue} · ${d.sales} sale(s)`;
});

function drawDonut(progress) {
  const { ctx, w, h } = setupCanvas("plan-donut");
  ctx.clearRect(0, 0, w, h);
  const byPlan = (overviewCache && overviewCache.by_plan) || {};
  const entries = Object.entries(byPlan);
  const total = entries.reduce((a, [, v]) => a + v, 0);
  const cx = w / 2, cy = h / 2, R = Math.min(w, h) / 2 - 8, r = R * 0.62;
  if (!total) {
    ctx.fillStyle = "#8b95a1";
    ctx.font = "13px system-ui";
    ctx.textAlign = "center";
    ctx.fillText("No active plans", cx, cy);
    $("plan-legend").innerHTML = "";
    return;
  }
  let a = -Math.PI / 2;
  entries.forEach(([plan, v]) => {
    const sweep = (v / total) * Math.PI * 2 * progress;
    ctx.beginPath();
    ctx.arc(cx, cy, R, a, a + sweep);
    ctx.arc(cx, cy, r, a + sweep, a, true);
    ctx.closePath();
    ctx.fillStyle = PLAN_COLORS[plan] || "#8b95a1";
    ctx.fill();
    a += (v / total) * Math.PI * 2;
  });
  ctx.fillStyle = "#ece9e2";
  ctx.font = "700 26px ui-monospace, monospace";
  ctx.textAlign = "center";
  ctx.fillText(total, cx, cy + 4);
  ctx.fillStyle = "#8b95a1";
  ctx.font = "11px system-ui";
  ctx.fillText("ACTIVE", cx, cy + 22);
  $("plan-legend").innerHTML = entries.map(([plan, v]) =>
    `<span><i style="background:${PLAN_COLORS[plan] || "#8b95a1"}"></i>${esc(plan)} · <b class="num">${v}</b></span>`
  ).join("");
}

function drawCharts() {
  if ($("view-overview").classList.contains("hidden")) return;
  if (reducedMotion) {
    drawArea(1);
    drawDonut(1);
    return;
  }
  chartProgress = 0;
  donutProgress = 0;
  const t0 = performance.now();
  (function frame(t) {
    const p = Math.min(1, (t - t0) / 800);
    drawArea(p);
    drawDonut(p);
    if (p < 1) requestAnimationFrame(frame);
  })(t0);
}
window.addEventListener("resize", () => drawCharts());

/* ---------- tables + actions ---------- */
function renderPending() {
  const rows = clientsCache.filter((c) => c.status === "pending");
  $("pending-rows").innerHTML = rows.map((c) => `
    <tr data-uid="${c.user_id}">
      <td><b>${esc("@" + (c.username || c.user_id))}</b><br><span class="muted num">${c.user_id}</span></td>
      <td>${esc(c.plan || "")} · <span class="num">$${esc(c.amount_usd)}</span></td>
      <td>${esc(c.method || "")}</td>
      <td class="num" title="${esc(c.tx_id || "")}">${esc(shortTx(c.tx_id))}</td>
      <td class="muted">${esc(c.verify_status || "manual")}<br><span style="font-size:11px">${esc((c.verify_message || "").slice(0, 60))}</span></td>
      <td><div class="rowbtns">
        <button class="btn small" data-act="approve" data-uid="${c.user_id}">Approve</button>
        <button class="btn small danger" data-act="reject" data-uid="${c.user_id}">Reject</button>
      </div></td>
    </tr>`).join("") || '<tr><td colspan="6" class="muted">Nothing pending — all clear.</td></tr>';
}

function renderClients() {
  const f = $("client-filter").value;
  const q = $("client-search").value.trim().toLowerCase();
  const rows = clientsCache.filter((c) =>
    (!f || c.status === f) &&
    (!q || String(c.username || "").toLowerCase().includes(q) || String(c.user_id).includes(q))
  );
  $("client-rows").innerHTML = rows.map((c) => `
    <tr data-uid="${c.user_id}">
      <td><b>${esc("@" + (c.username || c.user_id))}</b><br><span class="muted num">${c.user_id}</span></td>
      <td>${esc(c.plan || "")}</td>
      <td><span class="pill ${esc(c.status)}">${esc(c.status)}</span></td>
      <td class="num">${fmtDay(c.expires_at)}</td>
      <td class="num">${esc(c.amount_paid_total || "—")}</td>
      <td><div class="rowbtns">
        ${c.status === "pending" ? `<button class="btn small" data-act="approve" data-uid="${c.user_id}">Approve</button><button class="btn small danger" data-act="reject" data-uid="${c.user_id}">Reject</button>` : ""}
        ${c.status === "active" ? `<button class="btn small ghost" data-act="extend" data-uid="${c.user_id}">Extend</button><button class="btn small danger" data-act="revoke" data-uid="${c.user_id}">Revoke</button>` : ""}
        <button class="btn small ghost" data-act="message" data-uid="${c.user_id}">Message</button>
      </div></td>
    </tr>`).join("") || '<tr><td colspan="6" class="muted">No clients match.</td></tr>';
}
$("client-filter").addEventListener("input", renderClients);
$("client-search").addEventListener("input", renderClients);

document.addEventListener("click", async (ev) => {
  const btn = ev.target.closest("[data-act]");
  if (!btn) return;
  const uid = btn.dataset.uid;
  const act = btn.dataset.act;
  if (act === "message") {
    msgTarget = uid;
    $("msg-title").textContent = "Message @" + uid;
    $("msg-text").value = "";
    $("msg-overlay").classList.remove("hidden");
    return;
  }
  btn.disabled = true;
  try {
    const r = await post(`/api/clients/${uid}/${act}`);
    if (r.ok) {
      toast(`<b>${act}</b> done for <b>${uid}</b>`);
      await refresh();
      flashRow(uid);
    } else {
      toast(`Failed: ${esc(r.error || act)}`);
    }
  } catch (e) {
    toast("Request failed — try again.");
  }
  btn.disabled = false;
});

function flashRow(uid) {
  document.querySelectorAll(`tr[data-uid="${uid}"]`).forEach((tr) => {
    tr.classList.remove("flash");
    void tr.offsetWidth;
    tr.classList.add("flash");
  });
}

$("msg-cancel").addEventListener("click", () => $("msg-overlay").classList.add("hidden"));
$("msg-send").addEventListener("click", async () => {
  const text = $("msg-text").value.trim();
  if (!text || !msgTarget) return;
  $("msg-send").disabled = true;
  const r = await post(`/api/clients/${msgTarget}/message`, { text }).catch(() => ({ ok: false }));
  $("msg-send").disabled = false;
  $("msg-overlay").classList.add("hidden");
  toast(r.ok ? "Message <b>sent</b>" : "Message <b>failed</b> — user may have blocked the bot");
});

/* ---------- broadcast / settings / report ---------- */
$("broadcast-btn").addEventListener("click", async () => {
  const text = $("broadcast-text").value.trim();
  if (!text) return;
  $("broadcast-btn").disabled = true;
  $("broadcast-status").textContent = "Sending…";
  const r = await post("/api/broadcast", { text }).catch(() => ({ ok: false }));
  $("broadcast-btn").disabled = false;
  $("broadcast-status").textContent = r.ok ? `Done — ${r.sent} sent, ${r.failed} failed.` : "Failed.";
});

async function loadSettings() {
  const s = await get("/api/settings");
  $("demo-toggle").classList.toggle("on", !!s.demo_mode);
  $("daily-amount").value = s.daily_amount;
}
$("demo-toggle").addEventListener("click", () => $("demo-toggle").classList.toggle("on"));
$("settings-save").addEventListener("click", async () => {
  const r = await post("/api/settings", {
    demo_mode: $("demo-toggle").classList.contains("on"),
    daily_amount: parseFloat($("daily-amount").value),
  }).catch(() => ({ ok: false }));
  $("settings-status").textContent = r.ok ? "Saved." : ("Failed: " + (r.error || ""));
});

$("report-btn").addEventListener("click", async () => {
  const res = await api("/api/report.xlsx");
  const blob = await res.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "hire-report.xlsx";
  a.click();
  URL.revokeObjectURL(a.href);
});

/* ---------- websocket live ---------- */
function connectWS() {
  if (ws) { try { ws.close(); } catch (e) {} }
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws?token=${encodeURIComponent(token)}`);
  ws.onopen = () => {
    $("live-dot").classList.remove("off");
    $("live-text").textContent = "LIVE";
  };
  ws.onclose = () => {
    $("live-dot").classList.add("off");
    $("live-text").textContent = "OFFLINE";
    clearTimeout(wsTimer);
    wsTimer = setTimeout(connectWS, 3000);
  };
  ws.onerror = () => { try { ws.close(); } catch (e) {} };
  ws.onmessage = async (msg) => {
    let m;
    try { m = JSON.parse(msg.data); } catch (e) { return; }
    const d = m.data || {};
    if (m.event === "txid_received") {
      toast(`New TxID from <b>@${esc(d.username || d.user_id)}</b> · ${esc(d.plan || "")} $${esc(d.amount || "")}`);
      bump("card-pending");
    } else if (m.event === "client_activated") {
      toast(`<b>@${esc(d.username || d.user_id)}</b> activated · $${esc(d.amount || "")}`);
      bump("card-active");
      bump("card-revenue");
    } else if (m.event === "client_pending") {
      toast(`Payment pending review · <b>@${esc(d.username || d.user_id)}</b>`);
      bump("card-pending");
    } else if (m.event === "topup_needed") {
      toast(`Top-up needed · <b>@${esc(d.username || d.user_id)}</b>`);
    } else if (m.event === "client_updated") {
      bump("card-active");
    } else if (m.event === "settings_changed") {
      loadSettings();
      return;
    }
    await refresh();
    if (d.user_id) flashRow(d.user_id);
  };
}

async function refresh() {
  try {
    await loadOverview();
  } catch (e) { /* session expired -> logout() already ran */ }
}

/* ---------- auth / clock / init ---------- */
async function doLogin() {
  $("login-err").textContent = "";
  const res = await fetch("/api/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: $("login-user").value, password: $("login-pass").value }),
  });
  if (!res.ok) {
    $("login-err").textContent = "Wrong username or password.";
    return;
  }
  const data = await res.json();
  token = data.token;
  localStorage.setItem("hire_admin_token", token);
  enter();
}
function logout() {
  token = "";
  localStorage.removeItem("hire_admin_token");
  if (ws) { try { ws.close(); } catch (e) {} ws = null; }
  clearTimeout(wsTimer);
  $("app").classList.add("hidden");
  $("login").classList.remove("hidden");
}
async function enter() {
  $("login").classList.add("hidden");
  $("app").classList.remove("hidden");
  show("overview");
  await refresh();
  await loadSettings();
  connectWS();
}
$("login-btn").addEventListener("click", doLogin);
$("login-pass").addEventListener("keydown", (e) => { if (e.key === "Enter") doLogin(); });
$("logout-btn").addEventListener("click", logout);

setInterval(() => {
  $("clock").textContent = new Date().toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}, 1000);

if (token) enter();

