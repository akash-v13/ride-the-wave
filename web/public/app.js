const $ = (s) => document.querySelector(s);
const fmt = (n, d = 2) => (n == null ? "—" : Number(n).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d }));
const money = (n) => (n == null ? "—" : "$" + fmt(n));
const cls = (n) => (n > 0 ? "pos" : n < 0 ? "neg" : "");
const et = (iso) => (iso ? new Date(iso).toLocaleTimeString("en-US", { timeZone: "America/New_York", hour: "2-digit", minute: "2-digit" }) : "");
let token = localStorage.getItem("rtw_token") || "";

async function get(url) { const r = await fetch(url); if (!r.ok) throw new Error(url + " " + r.status); return r.json(); }

async function control(command, strategy) {
  if (!confirm(`${command} ${strategy}?`)) return;
  const r = await fetch("/api/controls", { method: "POST", headers: { "content-type": "application/json", authorization: token ? "Bearer " + token : "" }, body: JSON.stringify({ command, strategy }) });
  if (r.status === 401) { token = prompt("API token (RTW_API_TOKEN)") || ""; localStorage.setItem("rtw_token", token); return control(command, strategy); }
  const j = await r.json(); alert(j.queued ? `Queued: ${command} ${strategy} (#${j.id})` : JSON.stringify(j));
}

async function refresh() {
  const [status, positions, trades, strategies, health] = await Promise.all([
    get("/api/status"), get("/api/positions"), get("/api/trades?day=" + new Date().toLocaleDateString("en-CA", { timeZone: "America/New_York" })), get("/api/strategies"), get("/api/health"),
  ]);
  $("#bot").textContent = `· ${status.bot}${status.lastTick ? " · last tick " + et(status.lastTick) + " ET" : ""}`;
  const hb = status.heartbeat || {};
  $("#sub").textContent = `${status.today} · universe ${hb.universe ?? "—"} · ticks ${hb.tick ?? 0} · feature rows ${hb.feature_rows ?? 0}` + (health.alerts?.length ? " · ALERTS: " + health.alerts.join("; ") : "") + (status.risk?.halted ? " · RISK HALT: " + status.risk.halted : "");
  const acct = status.account || {};
  $("#tiles").innerHTML = [["Equity", money(acct.equity)], ["Cash", money(acct.cash)], ["Allocation", money(status.allocation)], ["Realised today (live)", `<span class="${cls(hb.realized_today)}">${money(hb.realized_today)}</span>`], ["Unrealised (live)", `<span class="${cls(hb.unrealized)}">${money(hb.unrealized)}</span>`]]
    .map(([k, v]) => `<div class="card"><div class="k">${k}</div><div class="v">${v}</div></div>`).join("");
  $("#strategies tbody").innerHTML = strategies.filter((s) => s.enabled).map((s) => { const l = s.live || {}; return `<tr><td>${s.id}</td><td>${s.mode}</td><td>${l.positions ?? "—"}</td><td>${l.trades ?? "—"}</td><td class="${cls(l.realized)}">${money(l.realized)}</td><td>${l.paused ? "yes" : "no"}</td><td>
    <button data-c="pause" data-s="${s.id}">Pause</button> <button data-c="resume" data-s="${s.id}">Resume</button> <button data-c="flatten" data-s="${s.id}">Flatten</button></td></tr>`; }).join("");
  $("#positions tbody").innerHTML = positions.length ? positions.map((p) => { const pnl = (p.last_price - p.entry_price) * p.qty; const pct = (p.last_price / p.entry_price - 1) * 100; return `<tr><td>${p.strategy}</td><td>${p.symbol}</td><td>${fmt(p.qty, 0)}</td><td>${fmt(p.entry_price)}</td><td>${fmt(p.last_price)}</td><td>${p.exit_trigger ? fmt(p.exit_trigger) : "<span class=muted>not armed</span>"}</td><td class="${cls(pnl)}">${money(pnl)}</td><td class="${cls(pct)}">${fmt(pct)}%</td></tr>`; }).join("") : `<tr><td colspan="8" class="muted">None</td></tr>`;
  $("#trades tbody").innerHTML = trades.length ? trades.map((t) => `<tr><td>${t.strategy}</td><td>${t.mode}</td><td>${t.symbol}</td><td>${et(t.entry_time)}</td><td>${et(t.exit_time)}</td><td>${fmt(t.entry_price)}</td><td>${fmt(t.exit_price)}</td><td class="${cls(t.pnl)}">${money(t.pnl)}</td><td class="${cls(t.pnl_pct)}">${fmt(t.pnl_pct)}%</td><td>${t.exit_reason}</td></tr>`).join("") : `<tr><td colspan="10" class="muted">None yet</td></tr>`;
  document.querySelectorAll("#strategies button").forEach((b) => (b.onclick = () => control(b.dataset.c, b.dataset.s)));
}

async function loadReports() {
  const days = await get("/api/reports");
  const pick = $("#reportPick"); pick.innerHTML = "";
  for (const d of days) for (const f of d.files) { const o = document.createElement("option"); o.value = `${d.day}/${f}`; o.textContent = `${d.day} ${f}`; pick.appendChild(o); }
  await showReport();
}
async function showReport() {
  const v = $("#reportPick").value; if (!v) { $("#report").textContent = "No reports yet."; return; }
  const [day, file] = v.split("/"); const r = await get(`/api/reports/${day}/${file}`); $("#report").textContent = r.markdown;
}
$("#reportPick").onchange = showReport; $("#reloadReport").onclick = loadReports;
refresh().catch((e) => ($("#sub").textContent = String(e))); loadReports().catch(() => {});
setInterval(() => refresh().catch(() => {}), 5000);
