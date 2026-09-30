/* Jarvis App. Kein Framework, keine Abhaengigkeit - laedt in unter 50 ms. */
"use strict";

/* ------------------------------------------------------------------ basis */

const $ = (id) => document.getElementById(id);
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const store = {
  get(key, fallback = null) {
    try { const raw = localStorage.getItem(key); return raw === null ? fallback : raw; }
    catch { return fallback; }
  },
  set(key, value) { try { localStorage.setItem(key, value); } catch { /* privater Modus */ } },
};

/* Token kommt einmal per URL, danach lebt es lokal weiter. */
const urlToken = new URLSearchParams(location.search).get("token");
if (urlToken) {
  store.set("jarvis-token", urlToken);
  document.cookie = `jarvis_token=${urlToken}; path=/; max-age=31536000; SameSite=Lax`;
  history.replaceState({}, "", location.pathname);
}
const TOKEN = store.get("jarvis-token", "") || "";
const headers = TOKEN ? { "X-Jarvis-Token": TOKEN } : {};

async function get(path) {
  const response = await fetch(path, { headers });
  if (!response.ok && response.status !== 503) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

async function post(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify(body || {}),
  });
  return response.json();
}

let toastTimer;
function toast(text) {
  const node = $("toast");
  node.textContent = text;
  node.classList.add("on");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => node.classList.remove("on"), 2600);
}

/* ---------------------------------------------------------------- formate */

const nf = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 2 });
const nf0 = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 0 });

const num = (value, digits = 2) => value == null || Number.isNaN(Number(value))
  ? "–"
  : new Intl.NumberFormat("de-DE", { minimumFractionDigits: digits,
      maximumFractionDigits: digits }).format(Number(value));

/* Grosse Betraege ohne Nachkomma, kleine Werte (kg, Kurse) mit - aber ohne
   ueberfluessige Nullen. */
function smart(value) {
  if (value == null || Number.isNaN(Number(value))) return "–";
  const n = Number(value);
  const digits = Math.abs(n) >= 1000 ? 0 : (Number.isInteger(n) ? 0 : 2);
  return new Intl.NumberFormat("de-DE", { maximumFractionDigits: digits }).format(n);
}

/* Vorzeichen traegt die Aussage, die Klasse faerbt nur nach. */
function delta(value, { suffix = "", digits = 2 } = {}) {
  const n = Number(value ?? 0);
  const cls = n > 0 ? "pos" : n < 0 ? "neg" : "flat";
  const sign = n > 0 ? "+" : "";
  return `<span class="delta ${cls}">${sign}${num(n, digits)}${suffix}</span>`;
}

/* Pfeil + Wort: die Richtung steht auch ohne Farbe da. */
function arrow(value) {
  const n = Number(value ?? 0);
  if (n > 0) return '<span class="delta pos" aria-label="steigend">&#9650;</span>';
  if (n < 0) return '<span class="delta neg" aria-label="fallend">&#9660;</span>';
  return '<span class="delta flat" aria-label="unveraendert">&#9644;</span>';
}

const STATUS_GLYPH = { OK: "&#9679;", VORSICHT: "&#9650;", STOP: "&#9632;" };
function statusBadge(status) {
  if (!status) return "";
  const key = String(status).toUpperCase();
  const cls = key === "STOP" ? "stop" : key === "VORSICHT" ? "vorsicht" : "ok";
  return `<span class="status ${cls}"><span aria-hidden="true">${STATUS_GLYPH[key] || "&#9679;"}</span>${esc(key)}</span>`;
}

const empty = (node, text) => { node.innerHTML = `<li class="empty">${esc(text)}</li>`; };

/* ------------------------------------------------------------- diagramme */

/* Sparkline: eine Serie, keine Achse, kein Legendenkasten - der Titel benennt sie.
   preserveAspectRatio="none" streckt die Flaeche, die Linie bleibt dank
   vector-effect (siehe CSS) ueberall 2 px stark. */
function sparkline(values, label = "Verlauf") {
  const points = (values || []).filter((v) => v != null && !Number.isNaN(Number(v))).map(Number);
  if (points.length < 2) return "";
  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = max - min || 1;
  const step = 100 / (points.length - 1);
  const y = (v) => 28 - ((v - min) / span) * 26;

  const line = points.map((v, i) =>
    `${i === 0 ? "M" : "L"}${(i * step).toFixed(2)},${y(v).toFixed(2)}`).join(" ");
  const area = `${line} L100,30 L0,30 Z`;
  const lastY = y(points[points.length - 1]);
  const first = points[0];
  const last = points[points.length - 1];

  return `<div class="sparkwrap" role="img"
      aria-label="${esc(label)}: ${points.length} Werte von ${smart(first)} auf ${smart(last)}">
    <svg class="spark" viewBox="0 0 100 30" preserveAspectRatio="none" aria-hidden="true">
      <path class="area" d="${area}"/><path d="${line}"/>
    </svg>
    <span class="sparkdot" style="top:${(lastY / 30 * 100).toFixed(2)}%"></span>
  </div>`;
}

/* Meter: ein Verhaeltnis gegen ein Limit - kein Tortendiagramm aus zwei Stuecken. */
function meter(percent, leftLabel, rightLabel) {
  const value = Math.max(0, Math.min(Number(percent) || 0, 100));
  return `<div class="meter">
    <div class="track" role="img" aria-label="${esc(leftLabel)} – ${value.toFixed(0)} Prozent">
      <div class="fill${value >= 100 ? " full" : ""}" style="width:${value}%"></div>
    </div>
    <div class="legend"><span>${leftLabel}</span><span>${rightLabel}</span></div>
  </div>`;
}

/* ------------------------------------------------------------- navigation */

const PAGES = ["heute", "trading", "markt", "ziele", "chat"];
let current = "heute";

function show(page) {
  if (!PAGES.includes(page)) page = "heute";
  current = page;
  PAGES.forEach((name) => $(`page-${name}`).classList.toggle("on", name === page));
  document.querySelectorAll("nav button").forEach((btn) => {
    if (btn.dataset.page === page) btn.setAttribute("aria-current", "page");
    else btn.removeAttribute("aria-current");
  });
  store.set("jarvis-tab", page);
  window.scrollTo({ top: 0, behavior: "instant" });
  loaders[page]?.();
}

document.querySelectorAll("nav button").forEach((btn) => {
  btn.onclick = () => show(btn.dataset.page);
});

/* ------------------------------------------------------------------ heute */

async function loadHeute() {
  let data;
  try { data = await get("/api/heute"); }
  catch (err) { toast("Nicht erreichbar: " + err.message); return; }
  if (data.offline) { toast("Offline – zeige letzten Stand"); return; }

  const s = data.status || {};
  $("hello").textContent = `Hallo ${s.name || ""}`.trim();
  $("headsub").textContent = [
    s.llm_bereit ? "bereit" : "Offline-Modus",
    s.marktdaten ? "Marktdaten" : "ohne Marktdaten",
    (s.kanaele || []).length ? s.kanaele.join(" + ") : "kein Push",
  ].join(" · ");
  const badge = $("badge");
  badge.hidden = !s.ungelesen;
  badge.textContent = s.ungelesen > 9 ? "9+" : s.ungelesen;

  renderPortfolio(data.portfolio);
  renderFocus(data);
  renderTasks(data.aufgaben);
  renderHabits(data.gewohnheiten);
}

function renderPortfolio(portfolio) {
  if (!portfolio || !portfolio.konten?.length) {
    $("total").textContent = "–";
    $("total-sub").textContent = "kein Konto hinterlegt";
    $("accounts").innerHTML = '<p class="empty">Konto anlegen: Tab Jarvis → "Leg ein Konto an mit 100000".</p>';
    return;
  }
  const currency = portfolio.konten[0].currency || "";
  $("total").textContent = nf0.format(portfolio.gesamt);
  $("total-sub").innerHTML = `${esc(currency)} · ${delta(portfolio.gesamt_pnl)} (${delta(portfolio.gesamt_pnl_pct, { suffix: "%" })})`;

  $("accounts").innerHTML = portfolio.konten.map((account) => {
    const guard = account.guard;
    const limit = guard?.daily_loss_limit || 0;
    const used = limit ? Math.max(0, limit - (guard.daily_room || 0)) / limit * 100 : 0;
    return `<div style="padding:12px 0;border-top:1px solid var(--line)">
      <div style="display:flex;gap:10px;align-items:baseline">
        <div class="grow">
          <strong>${esc(account.name)}</strong>
          <div class="sub">${esc(account.phase || account.broker || account.provider)}</div>
        </div>
        <div style="text-align:right">
          <div style="font-weight:640">${num(account.balance, 0)}</div>
          <div class="sub">${delta(account.pnl_pct, { suffix: "%" })}</div>
        </div>
      </div>
      ${sparkline(account.curve, `Kontoverlauf ${account.name}`)}
      ${guard ? `<div style="display:flex;gap:8px;align-items:center;margin-top:8px">
        ${statusBadge(guard.status)}
        <span class="sub grow">Puffer ${num(guard.room, 0)} ${esc(account.currency)}</span>
      </div>${meter(used, "Tagesrisiko genutzt", `${num(used, 0)} %`)}` : ""}
    </div>`;
  }).join("");
}

function renderFocus(data) {
  const items = [];
  const tasks = data.aufgaben || {};
  if (tasks.overdue?.length) items.push(`${tasks.overdue.length} überfällig – zuerst: <strong>${esc(tasks.overdue[0].title)}</strong>`);
  const top = (tasks.today || []).find((t) => t.priority === 1) || (tasks.today || [])[0];
  if (top) items.push(`Wichtigste Aufgabe: <strong>${esc(top.title)}</strong>`);

  const guard = data.trading?.guard;
  if (guard?.status === "STOP") items.push("Trading: <strong>Tageslimit erreicht</strong> – heute kein Trade mehr.");
  else if (guard?.status === "VORSICHT") items.push(`Trading: nur noch ${num(guard.room, 0)} ${esc(data.trading.currency || "")} Puffer.`);
  else if (Number(data.trading?.realized_yesterday) < 0) items.push("Gestern rot – erst Journal lesen, dann handeln.");

  (data.ziele || []).filter((g) => g.pace === "hinter Plan" || g.pace === "ueberfaellig")
    .slice(0, 2).forEach((g) => items.push(`Ziel hinter Plan: <strong>${esc(g.title)}</strong>`));

  const openHabit = (data.gewohnheiten || []).find((h) => !h.done_today);
  if (openHabit) items.push(`Offene Gewohnheit: ${esc(openHabit.name)}`);

  $("focus").innerHTML = items.length
    ? items.slice(0, 5).map((item) => `<li>${item}</li>`).join("")
    : '<li>Alles im Griff. Nichts brennt.</li>';
}

function renderTasks(groups) {
  const node = $("tasks");
  const rows = [
    ...(groups?.overdue || []).map((t) => [t, "überfällig"]),
    ...(groups?.today || []).map((t) => [t, "heute"]),
    ...(groups?.someday || []).map((t) => [t, "ohne Datum"]),
  ];
  if (!rows.length) return empty(node, "Nichts offen.");
  node.innerHTML = rows.slice(0, 12).map(([task, label]) => `
    <li><button class="check" data-task="${task.id}" aria-pressed="false"
        aria-label="${esc(task.title)} erledigen"></button>
      <span class="grow">${esc(task.title)}
        <span class="sub" style="display:block">${label}${task.due ? " · " + esc(task.due) : ""}</span>
      </span></li>`).join("");
  node.querySelectorAll(".check").forEach((btn) => {
    btn.onclick = async () => {
      btn.setAttribute("aria-pressed", "true");
      btn.innerHTML = "&#10003;";
      await post("/api/task/done", { id: Number(btn.dataset.task) });
      toast("Erledigt");
      setTimeout(loadHeute, 350);
    };
  });
}

function renderHabits(habits) {
  const node = $("habits");
  if (!habits?.length) return empty(node, "Keine Gewohnheiten angelegt.");
  node.innerHTML = habits.map((habit) => `
    <li><button class="check" data-habit="${esc(habit.name)}"
        aria-pressed="${habit.done_today}" aria-label="${esc(habit.name)} abhaken">${habit.done_today ? "&#10003;" : ""}</button>
      <span class="grow">${esc(habit.name)}
        <span class="sub" style="display:block">Streak ${habit.streak} Tage · Woche ${habit.this_week}/${habit.target_per_week}</span>
      </span></li>`).join("");
  node.querySelectorAll(".check").forEach((btn) => {
    btn.onclick = async () => {
      const done = btn.getAttribute("aria-pressed") !== "true";
      await post("/api/habit", { name: btn.dataset.habit, done });
      loadHeute();
    };
  });
}

/* ---------------------------------------------------------------- trading */

async function loadTrading() {
  let data;
  try { data = await get("/api/trading?days=30"); } catch { return; }
  const status = data.status || {};
  const currency = status.currency || "";
  const guard = status.guard;
  $("guard").innerHTML = statusBadge(guard?.status);

  $("trading-tiles").innerHTML = [
    ["Kontostand", num(status.balance, 0)],
    ["Heute", delta(status.realized_today, { digits: 0 })],
    ["Gestern", delta(status.realized_yesterday, { digits: 0 })],
    ["Puffer heute", guard ? num(guard.room, 0) : "–"],
    ["Bis Ziel", guard ? num(guard.target_remaining, 0) : "–"],
  ].map(([label, value]) =>
    `<div class="tile"><span class="label">${label}</span><span class="value">${value}</span></div>`).join("");

  const k = data.kennzahlen || {};
  $("stats-tiles").innerHTML = [
    ["Trades", k.trades ?? 0],
    ["Treffer", `${num(k.winrate, 1)} %`],
    ["Netto", delta(k.net_pnl, { digits: 0 })],
    ["Profit-Faktor", num(k.profit_factor, 2)],
    ["Ø R", num(k.avg_r, 2)],
    ["Max DD", num(k.max_drawdown?.absolute, 0)],
  ].map(([label, value]) =>
    `<div class="tile"><span class="label">${label}</span><span class="value">${value}</span></div>`).join("");

  const openNode = $("open-trades");
  const open = status.open_trades || [];
  if (!open.length) empty(openNode, "Keine offene Position.");
  else openNode.innerHTML = open.map((t) => `
    <li><span class="grow"><strong>${esc(t.symbol)}</strong> ${esc(t.direction)}
      <span class="sub" style="display:block">Entry ${num(t.entry, 5)} · SL ${num(t.stop_loss, 5)} · ${num(t.size, 2)} Lot</span>
    </span></li>`).join("");

  const tradeNode = $("trades");
  const trades = (data.trades || []).filter((t) => t.closed_at);
  if (!trades.length) empty(tradeNode, "Noch keine Trades im Journal.");
  else tradeNode.innerHTML = trades.slice(0, 12).map((t) => `
    <li><span class="grow"><strong>${esc(t.symbol)}</strong> ${esc(t.direction)}
      <span class="sub" style="display:block">${esc(String(t.closed_at).slice(0, 10))}${t.setup ? " · " + esc(t.setup) : ""}</span>
    </span>
    <span style="text-align:right">${delta(t.pnl)}
      <span class="sub" style="display:block">${t.r_multiple != null ? num(t.r_multiple, 2) + " R" : ""}</span>
    </span></li>`).join("");

  const breakdown = data.auswertung || {};
  const node = $("breakdown");
  const rows = [...(breakdown.symbol || []).slice(0, 4), ...(breakdown.setup || []).slice(0, 3)];
  if (!rows.length) empty(node, "Zu wenig Daten für eine Auswertung.");
  else {
    node.innerHTML = rows.map((row) => `
      <li><span class="grow">${esc(row.key)}
        <span class="sub" style="display:block">${plural(row.trades, "Trade", "Trades")} · ${num(row.winrate, 0)} % Treffer</span>
      </span>${arrow(row.net_pnl)} ${delta(row.net_pnl)}</li>`).join("");
    if ((breakdown.leaks || []).length) {
      node.innerHTML += breakdown.leaks.map((leak) =>
        `<li><span class="grow sub">${esc(leak)}</span></li>`).join("");
    }
  }
}

/* ------------------------------------------------------------------ markt */

async function loadMarkt() {
  let data;
  try { data = await get("/api/markt?days=3"); } catch { return; }

  const quotes = (data.kurse || []).filter((q) => q.price != null);
  const qNode = $("quotes");
  if (!quotes.length) empty(qNode, "Keine Kurse – FMP_API_KEY in der .env setzen.");
  else qNode.innerHTML = quotes.map((q) => `
    <li><span class="grow"><strong>${esc(q.symbol)}</strong>
      <span class="sub" style="display:block">${num(q.price, 4)}</span></span>
    ${arrow(q.change_pct)} ${delta(q.change_pct, { suffix: " %" })}</li>`).join("");

  const cNode = $("calendar");
  const events = data.kalender || [];
  if (!events.length) empty(cNode, "Keine wichtigen Termine.");
  else cNode.innerHTML = events.slice(0, 12).map((e) => `
    <li><span class="grow"><strong>${esc(e.event)}</strong>
      <span class="sub" style="display:block">${esc(e.country || "")} · ${esc(String(e.date || "").slice(5, 16).replace("T", " "))}${e.estimate != null ? " · Prognose " + esc(e.estimate) : ""}</span>
    </span></li>`).join("");

  const mNode = $("macro");
  const macro = Object.entries(data.makro || {});
  if (!macro.length) empty(mNode, "Keine Makrodaten.");
  else mNode.innerHTML = macro.map(([name, row]) => `
    <li><span class="grow">${esc(name)}
      <span class="sub" style="display:block">${esc(row.date || "")}</span></span>
    <span style="text-align:right">${num(row.value, 2)}
      <span class="sub" style="display:block">${esc(row.direction || "")}</span></span></li>`).join("");

  const nNode = $("news");
  const news = data.nachrichten || [];
  if (!news.length) empty(nNode, "Keine Schlagzeilen.");
  else nNode.innerHTML = news.slice(0, 10).map((n) => `
    <li><span class="grow">${n.url ? `<a href="${esc(n.url)}" target="_blank" rel="noopener" style="color:inherit">${esc(n.title)}</a>` : esc(n.title)}
      <span class="sub" style="display:block">${esc(n.site || "")}</span></span></li>`).join("");
}

/* ------------------------------------------------------------------ ziele */

async function loadZiele() {
  let data;
  try { data = await get("/api/ziele"); } catch { return; }
  const node = $("goals");
  const goals = data.ziele || [];
  if (!goals.length) {
    node.innerHTML = '<p class="empty">Noch kein Ziel. Tipp: „Ziel: 108000 auf FN-100k bis 31.12."</p>';
    return;
  }
  node.innerHTML = goals.map((goal) => {
    const pct = goal.progress_pct ?? 0;
    const unit = goal.unit || "";
    const paceWord = { "vor Plan": "vor Plan", "im Plan": "im Plan",
      "hinter Plan": "hinter Plan", "ueberfaellig": "überfällig",
      "erreicht": "erreicht" }[goal.pace] || "ohne Deadline";
    return `<div style="padding:13px 0;border-top:1px solid var(--line)">
      <div style="display:flex;gap:10px;align-items:baseline">
        <div class="grow"><strong>${esc(goal.title)}</strong>
          <div class="sub">${esc(paceWord)}${goal.days_left != null ? ` · noch ${goal.days_left} Tage` : ""}${goal.why ? " · " + esc(goal.why) : ""}</div>
        </div>
        <div style="font-weight:640">${num(pct, 0)} %</div>
      </div>
      ${meter(pct, `${smart(goal.current_value)} ${esc(unit)}`,
              goal.target_value != null ? `Ziel ${smart(goal.target_value)} ${esc(unit)}` : "")}
      ${goal.verlauf?.length > 1 ? sparkline(goal.verlauf.map((v) => v.value), goal.title) : ""}
      <div style="margin-top:9px;display:flex;gap:8px">
        <button class="ghost" data-progress="${goal.id}">Stand eintragen</button>
        ${goal.metric ? '<span class="sub" style="align-self:center">aktualisiert sich selbst</span>' : ""}
      </div>
    </div>`;
  }).join("");

  node.querySelectorAll("[data-progress]").forEach((btn) => {
    btn.onclick = async () => {
      const value = prompt("Neuer Stand?");
      if (value === null || value.trim() === "") return;
      await post("/api/goal/progress", { id: Number(btn.dataset.progress),
                                          value: Number(value.replace(",", ".")) });
      toast("Eingetragen");
      loadZiele();
    };
  });
}

/* ------------------------------------------------------------------- chat */

function addMessage(kind, text, tools) {
  const node = document.createElement("div");
  node.className = `msg ${kind}`;
  node.innerHTML = esc(text) + (tools?.length
    ? `<span class="tools">${esc(tools.join(", "))}</span>` : "");
  $("log").append(node);
  node.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

async function loadChat() {
  if ($("log").children.length) return;
  try {
    const history = await get("/api/verlauf?session=app&limit=20");
    history.forEach((m) => addMessage(m.role === "user" ? "me" : "j", m.content));
  } catch { /* leerer Verlauf ist auch ein Verlauf */ }
  renderSettings();
}

async function send(text) {
  if (!text.trim()) return;
  addMessage("me", text);
  $("send").disabled = true;
  $("chatstate").textContent = "denkt…";
  try {
    const reply = await post("/api/chat", { message: text, session: "app" });
    addMessage("j", reply.text || reply.error || "(keine Antwort)", reply.tools);
    if (reply.tools?.length) refresh();
  } catch (err) {
    addMessage("j", "Nicht erreichbar: " + err.message);
  } finally {
    $("send").disabled = false;
    $("chatstate").textContent = "";
  }
}

$("chatform").onsubmit = (event) => {
  event.preventDefault();
  const input = $("msg");
  const text = input.value;
  input.value = "";
  send(text);
};

$("chips").querySelectorAll(".chip").forEach((chip) => {
  chip.onclick = () => send(chip.textContent);
});

async function renderSettings() {
  let status;
  try { status = await get("/api/status"); } catch { return; }
  $("settings").innerHTML = [
    ["Sprachmodell", status.llm_bereit ? status.llm : "Offline-Modus (kein Key)"],
    ["Marktdaten", status.marktdaten ? "verbunden" : "FMP_API_KEY fehlt"],
    ["Push", (status.kanaele || []).join(", ") || "nicht eingerichtet"],
    ["Konten", status.konten],
    ["Aktive Ziele", status.aktive_ziele],
    ["Version", status.version],
  ].map(([label, value]) =>
    `<li><span class="grow">${esc(label)}</span><span class="sub">${esc(value)}</span></li>`).join("");
}

/* ------------------------------------------------------------- aktionen */

$("btn-sync").onclick = async () => {
  const btn = $("btn-sync");
  btn.classList.add("busy");
  try {
    const result = await post("/api/sync", {});
    toast(result.fehler?.length ? result.fehler[0].slice(0, 90)
                                : `${result.konten.length} Konto/Konten aktualisiert`);
    refresh();
  } catch (err) { toast("Fehlgeschlagen: " + err.message); }
  finally { btn.classList.remove("busy"); }
};

$("btn-bell").onclick = async () => {
  const data = await get("/api/notifications?limit=12");
  const lines = (data.meldungen || []).map((m) => `• ${m.title}`).join("\n");
  alert(lines || "Keine Meldungen.");
  await post("/api/notifications/read", {});
  $("badge").hidden = true;
};

$("btn-addtask").onclick = async () => {
  const title = prompt("Neue Aufgabe?");
  if (!title?.trim()) return;
  const due = prompt("Wann fällig? (heute, morgen, freitag, 24.12. – leer lassen für später)") || "";
  await post("/api/task", { title, due });
  toast("Angelegt");
  loadHeute();
};

$("btn-addgoal").onclick = async () => {
  const title = prompt("Was ist dein Ziel?");
  if (!title?.trim()) return;
  const target = prompt("Zielwert? (Zahl, leer lassen wenn ohne)") || "";
  const unit = target ? (prompt("Einheit? (USD, kg, Trades …)") || "") : "";
  const deadline = prompt("Bis wann? (2026-12-31, leer lassen für offen)") || "";
  await post("/api/goal", {
    title,
    target_value: target ? Number(target.replace(",", ".")) : undefined,
    unit, deadline,
  });
  toast("Ziel angelegt");
  loadZiele();
};

$("btn-balance").onclick = async () => {
  const portfolio = await get("/api/portfolio");
  const names = (portfolio.konten || []).map((a) => a.name);
  if (!names.length) return toast("Erst ein Konto anlegen");
  const account = names.length === 1 ? names[0] : prompt(`Welches Konto?\n${names.join("\n")}`);
  if (!account) return;
  const balance = prompt(`Neuer Stand für ${account}?`);
  if (!balance) return;
  await post("/api/balance", { account, balance: Number(balance.replace(",", ".")) });
  toast("Stand aktualisiert");
  loadHeute();
};

$("btn-brief").onclick = async () => {
  const node = $("brief");
  node.textContent = "erzeuge…";
  try {
    const brief = await get("/api/brief");
    node.textContent = brief.markdown;
  } catch (err) { node.textContent = "Fehler: " + err.message; }
};

$("btn-alerts").onclick = async () => {
  const result = await post("/api/alerts", { send: true });
  toast(result.anzahl ? `${result.anzahl} Warnung(en) verschickt` : "Nichts Dringendes.");
};

$("btn-theme").onclick = () => {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  store.set("jarvis-theme", next);
};
document.documentElement.dataset.theme = store.get("jarvis-theme", "dark");

/* Installations-Angebot (Android/Chrome). iOS: "Zum Startbildschirm hinzufuegen". */
let installPrompt = null;
window.addEventListener("beforeinstallprompt", (event) => {
  event.preventDefault();
  installPrompt = event;
  $("btn-install").hidden = false;
});
$("btn-install").onclick = async () => {
  if (!installPrompt) return;
  installPrompt.prompt();
  installPrompt = null;
  $("btn-install").hidden = true;
};

/* ------------------------------------------------------- leben & laden */

const loaders = {
  heute: loadHeute, trading: loadTrading, markt: loadMarkt,
  ziele: loadZiele, chat: loadChat,
};

function refresh() { loaders[current]?.(); }

/* Der Server meldet sich von selbst, sobald sich etwas aendert. */
function connectStream() {
  if (!window.EventSource) return;
  const url = "/api/stream" + (TOKEN ? `?token=${encodeURIComponent(TOKEN)}` : "");
  const source = new EventSource(url);
  source.onmessage = (event) => {
    let message;
    try { message = JSON.parse(event.data); } catch { return; }
    if (message.event === "alert" && message.payload) {
      toast(message.payload.title || "Neue Meldung");
      navigator.serviceWorker?.controller?.postMessage({
        type: "notify", title: message.payload.title, body: message.payload.body,
      });
    }
    refresh();
  };
  source.onerror = () => { source.close(); setTimeout(connectStream, 15000); };
}

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") refresh();
});

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js").catch(() => {}));
}

show(new URLSearchParams(location.search).get("tab") || store.get("jarvis-tab", "heute"));
connectStream();
setInterval(() => { if (document.visibilityState === "visible") refresh(); }, 120000);
