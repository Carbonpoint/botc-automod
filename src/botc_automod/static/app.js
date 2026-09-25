"use strict";
// Clocktower Automod browser client. The server sends a personal view;
// this file only renders it and sends the player's actions back.

const app = document.getElementById("app");
const toastEl = document.getElementById("toast");
let S = null;               // latest state from the server
let ws = null, wsTries = 0, wsOpen = false;
let almanac = null;
const ui = { tab: "me", picks: [], taskId: null, nominate: null, form: {}, editions: null,
             grid: null, lastLog: 0, seenTask: null, pendingRender: false };

// ---------- helpers ----------
const esc = s => String(s ?? "").replace(/[&<>"']/g, c =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const session = {
  get() { try { return JSON.parse(localStorage.getItem("botc") || "null"); } catch { return null; } },
  set(v) { try { localStorage.setItem("botc", JSON.stringify(v)); } catch {} },
  clear() { try { localStorage.removeItem("botc"); } catch {} },
};
function toast(msg, kind = "") {
  toastEl.textContent = msg; toastEl.className = kind; toastEl.hidden = false;
  clearTimeout(toast.t); toast.t = setTimeout(() => (toastEl.hidden = true), 3500);
}
function send(msg) {
  if (ws && wsOpen) ws.send(JSON.stringify(msg));
  else toast("Not connected. Reconnecting...");
}
async function api(path, body) {
  const r = await fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" },
                                       body: JSON.stringify(body) } : {});
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.detail || "Request failed");
  return j;
}
const byId = id => S.players.find(p => p.id === id);
const nameOf = id => byId(id)?.name ?? "?";
const fv = (id, def = "") => ui.form[id] ?? def;
const opt = (id, value, label, def) => `<option value="${esc(value)}" ${fv(id, def) === value ? "selected" : ""}>${esc(label)}</option>`;
const playerSelect = (id, ids, blank = false) => `<select id="${id}">${blank ? opt(id, "", "—", "") : ""}${
  ids.map(x => opt(id, x, nameOf(x), blank ? "" : ids[0])).join("")}</select>`;
const roleSelect = (id, roles, blank = false) => `<select id="${id}">${blank ? opt(id, "", "—", "") : ""}${
  roles.map(r => opt(id, r.id, r.name, blank ? "" : roles[0]?.id)).join("")}</select>`;
const alivePlayers = () => S.players.filter(p => p.seat != null && p.alive).map(p => p.id);
const fmt = t => t == null ? "" : `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`;

// ---------- connection ----------
function connect() {
  const s = session.get();
  if (!s) return render();
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws/${s.code}?token=${encodeURIComponent(s.token)}`);
  ws.onopen = () => { wsOpen = true; wsTries = 0; render(); };
  ws.onmessage = ev => {
    const m = JSON.parse(ev.data);
    if (m.type === "state") { onState(m.state); }
    else if (m.type === "timer") { if (S) { S.game.timer = m.timer; S.game.paused = m.paused; drawTimer(); } }
    else if (m.type === "error") toast(m.message);
    else if (m.type === "gone") { session.clear(); S = null; toast("That game no longer exists."); render(); }
  };
  ws.onclose = ev => {
    wsOpen = false;
    if (ev.code === 4004 || ev.code === 4001) { session.clear(); S = null; render(); return; }
    render();
    setTimeout(connect, Math.min(8000, 500 * 2 ** wsTries++));
  };
}
setInterval(() => { if (ws && wsOpen) ws.send('{"type":"ping"}'); }, 25000);

function onState(state) {
  const prev = S;
  S = state;
  if (!almanac || almanac.id !== S.game.edition.id)
    api(`/api/editions/${S.game.edition.id}`).then(a => { almanac = a; render(); });
  const task = S.task;
  if (task && task.id !== ui.seenTask) {
    ui.seenTask = task.id; ui.picks = [];
    if (navigator.vibrate) navigator.vibrate(120);
  }
  if (prev && prev.game.phase !== S.game.phase) {
    ui.nominate = null;
    if (S.game.phase === "vote" && navigator.vibrate) navigator.vibrate([80, 60, 80]);
  }
  if (prev?.game.phase === "lobby" && S.game.phase !== "lobby") { ui.tab = S.me.storyteller ? "grim" : "me"; keepAwake(); }
  if (!prev && S.me.storyteller && ui.tab === "me") ui.tab = "grim";
  if (S.me.log.length > ui.lastLog && ui.tab !== "me") ui.logBadge = true;
  if (ui.tab === "me") ui.lastLog = S.me.log.length;
  render();
}

let wakeLock = null;
async function keepAwake() {
  try { if ("wakeLock" in navigator && !wakeLock) wakeLock = await navigator.wakeLock.request("screen");
        wakeLock?.addEventListener("release", () => (wakeLock = null)); } catch {}
}
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && S && S.game.phase !== "lobby") keepAwake();
});

// ---------- render ----------
function render() {
  // Do not wipe a field the player is typing in; draw again when they leave it.
  const a = document.activeElement;
  if (a && app.contains(a) && (a.tagName === "INPUT" || a.tagName === "SELECT" || a.tagName === "TEXTAREA")) {
    ui.pendingRender = true; return;
  }
  ui.pendingRender = false;
  if (!session.get()) { app.innerHTML = homeView(); loadGames(); return; }
  if (!S) { app.innerHTML = `<div class="card">Connecting...</div>`; return; }
  const g = S.game;
  let html = topBar();
  if (g.phase === "lobby") html += lobbyView();
  else {
    if (g.phase === "ended") html += endView();
    html += ({ me: meView, grim: grimView, town: townView, almanac: almanacView, log: logView, host: hostView }[ui.tab] || meView)();
    html += tabsView();
    if (g.phase === "night" && !S.me.storyteller) html += nightView();
  }
  app.innerHTML = html;
  drawTimer();
}
document.addEventListener("focusout", () => setTimeout(() => ui.pendingRender && render(), 0));

function topBar() {
  const g = S.game;
  let sub = "";
  if (g.phase === "night") sub = "Night tasks";
  else if (g.phase === "day") sub = "Discussion";
  else if (g.phase === "nominations") sub = "Nominations open";
  else if (g.phase === "defense") sub = `${nameOf(S.day.current?.nominee)} is nominated`;
  else if (g.phase === "vote") sub = `Vote on ${nameOf(S.day.current?.nominee)}`;
  else if (g.phase === "lobby") sub = `${g.edition.name} lobby`;
  else if (g.phase === "setup") sub = "The Storyteller is preparing";
  if (g.phase === "night" && g.stage.startsWith("review")) sub = "The Storyteller is resolving the night";
  return `<div class="top"><div class="phase">${esc(g.label)} <span class="code">${esc(g.code)}</span>
    <small>${esc(sub)}${wsOpen ? "" : ' <span class="conn">offline</span>'}</small></div>
    <div id="timer" class="timer"></div></div>`;
}
function drawTimer() {
  const el = document.getElementById("timer");
  if (!el || !S) return;
  const t = S.game.timer;
  el.textContent = S.game.paused ? `${fmt(t)} ⏸` : fmt(t);
  el.className = "timer" + (S.game.paused ? " paused" : t != null && t <= 10 ? " low" : "");
}

// ---------- home ----------
function homeView() {
  return `<h1 style="margin-top:24px">Clocktower Automod</h1>
  <p class="muted">Blood on the Clocktower with an automatic storyteller. Everyone plays; one player hosts.</p>
  <div class="card stack">
    <label>Your name<input id="name" maxlength="24" autocomplete="nickname" placeholder="Name shown to the table"></label>
    <button class="primary big" data-act="host">Host a new game</button>
  </div>
  <div class="card stack">
    <h3>Join a game</h3>
    <div class="row"><input id="code" class="grow" maxlength="4" placeholder="Code, e.g. KQTR" style="text-transform:uppercase">
      <button data-act="joincode">Join</button></div>
    <div id="games" class="stack"></div>
  </div>`;
}
async function loadGames() {
  try {
    const list = await api("/api/games");
    const el = document.getElementById("games");
    if (!el) return;
    el.innerHTML = list.length ? list.map(g => `<button class="big" data-act="join" data-code="${esc(g.code)}">
      Join ${esc(g.host)}'s game <span class="code">${esc(g.code)}</span>
      <span class="muted small">· ${g.players} player${g.players === 1 ? "" : "s"}</span></button>`).join("")
      : `<p class="muted small">No open games on this server yet.</p>`;
  } catch {}
}
setInterval(() => { if (!session.get()) loadGames(); }, 4000);

// ---------- lobby ----------
function seatMap(opts = {}) {
  const room = S.room, layout = S.layout;
  const flat = room.shape !== "circle";
  const ratio = room.shape === "grid" && room.rows ? `aspect-ratio:${room.cols}/${room.rows}` : "";
  const bySeat = {}; S.players.forEach(p => { if (p.seat != null) bySeat[p.seat] = p; });
  const cur = S.day.current, block = S.day.block;
  const seats = layout.map(s => {
    const p = bySeat[s.index];
    const cls = ["seat"];
    if (!p) cls.push("empty");
    else {
      if (p.id === S.me.id) cls.push("me");
      if (!p.alive) cls.push("dead");
      if (!p.connected) cls.push("off");
      if (block && block.pid === p.id) cls.push("block");
      if (cur && cur.nominee === p.id) cls.push("nominee");
    }
    const label = p ? `${esc(p.name)}${p.is_host ? " ★" : ""}${!p.alive && p.ghost_vote ? ' <span class="ghost">●</span>' : ""}`
                    : (opts.lobby ? "Sit here" : "");
    const act = opts.act && (p ? opts.act !== "seat" : opts.act === "seat") ? `data-act="${opts.act}" data-seat="${s.index}" data-pid="${p?.id ?? ""}"` : "";
    return `<button class="${cls.join(" ")}" style="left:${s.x * 100}%;top:${s.y * 100}%" ${act}>
      <span class="n">${s.index + 1}</span>${label}</button>`;
  }).join("");
  return `<div class="map ${flat ? "flat" : ""} ${layout.length > 12 ? "dense" : ""}" style="${ratio}">${seats}</div>`;
}

function lobbyView() {
  const me = S.me, g = S.game;
  const seated = S.players.filter(p => p.seat != null).length;
  const local = ["localhost", "127.0.0.1", "::1", "[::1]"].includes(location.hostname);
  const joinUrl = local && ui.lanUrl ? ui.lanUrl : `${location.origin}/`;
  if (local && !ui.lanUrl) api("/api/info").then(r => { ui.lanUrl = r.join_url; render(); }).catch(() => {});
  let html = "";
  if (me.is_host) {
    html += `<div class="card row"><img class="qr" alt="QR code to join" src="/api/qr?url=${encodeURIComponent(joinUrl)}">
      <div class="grow"><h3>Invite players</h3><p>Open <b>${esc(joinUrl)}</b> on the same Wi-Fi, then join code
      <span class="code">${esc(g.code)}</span>.</p></div></div>`;
  }
  if (me.is_host) {
    if (!ui.editions) api("/api/editions").then(e => { ui.editions = e; render(); }).catch(() => {});
    html += `<div class="card stack"><h3>Edition</h3>
      ${ui.editions ? seg("edition", ui.editions.map(e => [e.id, e.name]), g.edition.id) : ""}</div>`;
  } else html += `<div class="card"><p>Edition: <b>${esc(g.edition.name)}</b></p></div>`;
  if (me.is_host) html += `<div class="card stack"><h3>Storyteller</h3>
    ${seg("mode", [["auto", "Automated"], ["human", "Human (me)"]], g.mode)}
    <p class="small muted">${g.mode === "human"
      ? "You run the game and do not play. You see the Grimoire, check the deal, and approve each night's results."
      : "The server runs the game. You play like everyone else and only control the timer."}</p></div>`;
  else html += `<div class="card"><p>Storyteller: <b>${g.mode === "human" ? esc(S.players.find(p => p.is_host)?.name) : "automated"}</b></p></div>`;
  html += `<div class="card"><h3>Seats</h3><p class="muted small">${me.storyteller ? "Players tap an empty seat to sit there." : "Tap an empty seat to sit there."}
    Seats run clockwise: neighbours matter.</p>${seatMap({ lobby: true, act: me.storyteller ? "" : "seat" })}
    ${me.seat != null ? `<button data-act="unseat">Leave my seat</button>` : ""}</div>`;
  if (!me.storyteller) html += `<div class="card stack"><h3>Your preferences</h3>
    <p class="small muted">The deal is random, but it tries to give you what you ask for.</p>
    <p>Which team would you like?</p>${seg("team", [["good", "Good"], ["evil", "Evil"], ["any", "No preference"]], me.prefs.team)}
    <p>How do you want to play?</p>${seg("style", [["chill", "Chill"], ["think", "Thinking"], ["any", "No preference"]], me.prefs.style)}
    <p class="small ${me.ready ? "" : "muted"}">${me.ready ? "✓ Saved." : "Tap your choices to save them."}</p></div>`;
  html += `<div class="card"><h3>Players (${S.players.length})</h3><ul class="log">${S.players.map(p => `<li class="row">
    <span class="grow">${esc(p.name)}${p.is_host ? (g.mode === "human" ? " ★ storyteller" : " ★ host") : ""} ${p.seat != null ? `<span class="muted small">seat ${p.seat + 1}</span>` : p.is_host && g.mode === "human" ? "" : '<span class="muted small">not seated</span>'}
    ${p.ready ? "✓" : ""} ${p.connected ? "" : '<span class="conn">offline</span>'}</span>
    ${me.is_host && !p.is_host ? `<button class="danger" data-act="kick" data-pid="${p.id}">Remove</button>` : ""}</li>`).join("")}</ul></div>`;
  if (me.is_host) html += hostLobby(seated);
  else html += `<p class="muted">Waiting for the host to start the game.</p>`;
  html += `<button class="danger" data-act="leave">Leave this game</button>`;
  return html;
}
function seg(name, options, value) {
  return `<div class="seg">${options.map(([v, l]) =>
    `<button class="${v === value ? "sel" : ""}" data-act="pref" data-k="${name}" data-v="${v}">${l}</button>`).join("")}</div>`;
}

function hostLobby(seated) {
  const g = S.game, r = { ...S.room, shape: ui.shapeDraft || S.room.shape };
  const shapes = [["circle", "Circle"], ["horseshoe", "Horseshoe"], ["square", "Square"], ["grid", "Grid"]];
  let html = `<div class="card stack"><h3>Room (host)</h3>
    <div class="seg">${shapes.map(([v, l]) => `<button class="${r.shape === v ? "sel" : ""}" data-act="shape" data-v="${v}">${l}</button>`).join("")}</div>`;
  if (r.shape !== "grid") {
    html += `<div class="row"><span>Seats</span><button data-act="seats" data-d="-1">−</button>
      <b>${r.seats}</b><button data-act="seats" data-d="1">+</button>
      <span class="muted small">Set this to the number of chairs.</span></div>`;
  } else {
    if (!ui.grid) ui.grid = { rows: r.rows || 4, cols: r.cols || 5, cells: (r.cells || []).map(c => [...c]) };
    const G = ui.grid;
    const order = {}; G.cells.forEach(([y, x], i) => (order[`${y},${x}`] = i + 1));
    let cells = "";
    for (let y = 0; y < G.rows; y++) for (let x = 0; x < G.cols; x++) {
      const n = order[`${y},${x}`];
      cells += `<button class="${n ? "on" : ""}" data-act="cell" data-y="${y}" data-x="${x}">${n ?? ""}</button>`;
    }
    html += `<div class="row">Rows <button data-act="gdim" data-k="rows" data-d="-1">−</button><b>${G.rows}</b>
      <button data-act="gdim" data-k="rows" data-d="1">+</button>
      Columns <button data-act="gdim" data-k="cols" data-d="-1">−</button><b>${G.cols}</b>
      <button data-act="gdim" data-k="cols" data-d="1">+</button></div>
      <p class="small muted">Tap the squares that are seats, going clockwise around the room. Tap again to remove.</p>
      <div class="grid" style="grid-template-columns:repeat(${G.cols},1fr)">${cells}</div>
      <div class="row"><button data-act="gclear">Clear</button>
      <button class="primary" data-act="gapply" ${G.cells.length < g.min_players ? "disabled" : ""}>Use these ${G.cells.length} seats</button></div>`;
  }
  const n = S.players.length - (g.mode === "human" ? 1 : 0);
  const ok = n >= g.min_players && n <= g.max_players && seated === n;
  html += `<button class="primary big" data-act="start" ${ok ? "" : "disabled"}>Start the game</button>
    <p class="small muted">${n < g.min_players ? `Need at least ${g.min_players} players.` :
      n > g.max_players ? `At most ${g.max_players} players.` : seated < n ? "Everyone must take a seat." :
      g.mode === "human" ? "You check the characters before the first night." : "Everyone gets a character when you start."}</p></div>`;
  return html;
}

// ---------- game tabs ----------
function tabsView() {
  const tabs = S.me.storyteller ? [["grim", "Grimoire"], ["town", "Town"], ["almanac", "Characters"], ["log", "Log"]]
                                : [["me", "Me"], ["town", "Town"], ["almanac", "Characters"], ["log", "Log"]];
  if (S.me.is_host) tabs.push(["host", "Host"]);
  return `<nav class="tabs">${tabs.map(([k, l]) => `<button class="${ui.tab === k ? "on" : ""}" data-act="tab" data-v="${k}">${l}${
    k === "me" && ui.logBadge ? '<span class="badge"></span>' : ""}${
    k === "town" && ["nominations", "vote", "defense"].includes(S.game.phase) && ui.tab !== "town" ? '<span class="badge"></span>' : ""}</button>`).join("")}</nav>`;
}

function roleCard(r, team = r.team) {
  return `<div class="card role ${team}"><div class="type">${esc(r.type)} · you are <span class="tag-${team}">${team}</span></div>
    <h2>${esc(r.name)}</h2><p>${esc(r.ability)}</p>${r.tip ? `<p class="small muted">${esc(r.tip)}</p>` : ""}</div>`;
}

function wikiDetails(id, open = false) {
  const w = almanac?.roles.find(r => r.id === id)?.wiki;
  if (!w || !w.summary) return "";
  const list = (h, items) => items?.length ? `<h3>${h}</h3><ul>${items.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : "";
  return `<details ${open ? "open" : ""}><summary>More about this character</summary>
    ${w.flavour ? `<p class="muted"><i>“${esc(w.flavour)}”</i></p>` : ""}${list("How it works", w.summary)}
    ${list("Examples", w.examples)}${list("Tips", w.tips)}
    ${S.me.storyteller ? list("How to run", w.how_to_run) : ""}
    <p class="small"><a href="${esc(w.source)}" target="_blank" rel="noopener">Official wiki page</a></p></details>`;
}

function meView() {
  const me = S.me;
  if (!me.role) return `<div class="card"><p>The Storyteller is preparing the game. Your character appears here soon.</p></div>`;
  let html = forcedActions();
  html += roleCard(me.role, me.team || me.role.team).replace(/<\/div>$/, wikiDetails(me.role.id) + "</div>");
  html += `<div class="card"><p>You are <b>${me.alive ? "alive" : "dead"}</b>.
    ${me.alive ? "" : me.ghost_vote ? "You still have your one ghost vote." : "You have used your ghost vote."}</p></div>`;
  html += `<div class="card"><h3>Your notebook</h3><p class="small muted">Everything the storyteller has told you in private.</p>
    <ul class="log">${[...me.log].reverse().map(e => `<li><span class="lbl">${esc(e.label)}</span>${esc(e.text)}</li>`).join("")}</ul></div>`;
  return html;
}

function townView() {
  const g = S.game, d = S.day, me = S.me;
  let html = `<div class="card">${seatMap({ act: "player" })}
    <p class="small muted">★ host · ● ghost vote left · red ring: about to die${d.needed ? ` · ${d.needed} votes needed to execute` : ""}</p></div>`;
  if (g.phase === "vote" && d.current && me.seat != null) html += voteCard();
  if (g.phase === "defense" && d.current)
    html += `<div class="card"><h2>${esc(nameOf(d.current.nominator))} nominates ${esc(nameOf(d.current.nominee))}</h2>
      <p>Accusation, then defence. The vote opens when the timer ends.</p></div>`;
  if (d.block) html += `<div class="card"><b>${esc(nameOf(d.block.pid))}</b> is about to die with ${d.block.votes} votes.</div>`;
  if (g.phase === "nominations") {
    const canNom = me.seat != null && me.alive && !d.nominators.includes(me.id);
    html += `<div class="card stack"><h3>Nominate</h3>${canNom ? (ui.nominate ?
      `<p>Nominate <b>${esc(nameOf(ui.nominate))}</b>?</p><div class="row"><button class="primary" data-act="nominate-ok">Yes, nominate</button>
       <button data-act="nominate-cancel">Cancel</button></div>` :
      `<p>Tap a player on the map to nominate them.</p>`) :
      `<p class="muted">${me.seat == null ? "Players nominate from their phones." : me.alive ? "You have already nominated today." : "Dead players cannot nominate."}</p>`}
      ${d.nominees.length ? `<p class="small muted">Already nominated today: ${d.nominees.map(nameOf).map(esc).join(", ")}</p>` : ""}</div>`;
  }
  html += (me.day_actions || []).filter(a => !a.forced).map(dayActionCard).join("");
  if (d.history.length) html += `<div class="card"><h3>Votes today</h3><ul class="log">${d.history.map(h =>
    `<li>${esc(nameOf(h.nominator))} → ${esc(nameOf(h.nominee))}: <b>${h.votes}</b>
     <span class="small muted">${h.yes.map(nameOf).map(esc).join(", ")}</span></li>`).join("")}</ul></div>`;
  return html;
}

function forcedActions() {
  return (S.me.day_actions || []).filter(a => a.forced).map(dayActionCard).join("");
}

function dayActionCard(a) {
  const id = `da-${a.key}`;
  const roles = almanac?.roles || [];
  let form = "";
  if (a.kind === "target") {
    form = playerSelect(`${id}-target`, a.candidates || alivePlayers());
  } else if (a.kind === "statement" || a.kind === "question") {
    const k = fv(`${id}-kind`, "is_evil");
    form = `<select id="${id}-kind">${opt(`${id}-kind`, "is_evil", "[player] is evil", "is_evil")}
        ${opt(`${id}-kind`, "is_role", "[player] is the [character]", "is_evil")}
        ${opt(`${id}-kind`, "is_type", "[player] is a [type]", "is_evil")}
        ${opt(`${id}-kind`, "in_play", "The [character] is in play", "is_evil")}
        ${opt(`${id}-kind`, "text", "Something else (free text)", "is_evil")}</select>
      ${k !== "in_play" && k !== "text" ? playerSelect(`${id}-player`, S.players.filter(p => p.seat != null).map(p => p.id)) : ""}
      ${k === "is_role" || k === "in_play" ? roleSelect(`${id}-role`, roles) : ""}
      ${k === "is_type" ? `<select id="${id}-type">${["townsfolk", "outsider", "minion", "demon"].map(t => opt(`${id}-type`, t, t, "demon")).join("")}</select>` : ""}
      ${k === "text" ? `<input id="${id}-text" maxlength="200" value="${esc(fv(`${id}-text`))}" placeholder="Your statement">` : ""}`;
  } else if (a.kind === "guesses") {
    const ids = S.players.filter(p => p.seat != null).map(p => p.id);
    form = [0, 1, 2, 3, 4].map(i => `<div class="row">${playerSelect(`${id}-p${i}`, ids, true)}${roleSelect(`${id}-r${i}`, roles, true)}</div>`).join("");
  }
  return `<div class="card stack ${a.forced ? "read" : ""}"><h3>${esc(a.label)}</h3><p class="small muted">${esc(a.help || "")}
    ${a.public ? " Everyone sees this." : " Only you see the answer."}</p><div class="stack">${form}</div>
    <button class="${a.forced ? "primary big" : ""}" data-act="dayact" data-key="${esc(a.key)}" data-kind="${esc(a.kind)}">${a.kind === "visit" ? "Visit" : "Confirm"}</button></div>`;
}

function dayPayload(key, kind) {
  const id = `da-${key}`, val = x => document.getElementById(`${id}-${x}`)?.value;
  if (kind === "target") return { target: val("target") };
  if (kind === "statement" || kind === "question") {
    const k = val("kind");
    return k === "text" ? { kind: "text", text: val("text") || "" } : { kind: k, player: val("player"), role: val("role"), type: val("type") };
  }
  if (kind === "guesses") return { guesses: [0, 1, 2, 3, 4].map(i => ({ player: val(`p${i}`), character: val(`r${i}`) })).filter(x => x.player && x.character) };
  return {};
}

function voteCard() {
  const d = S.day, me = S.me, cur = d.current;
  const canVote = me.alive || me.ghost_vote;
  const voted = cur.voted.length, total = S.players.filter(p => p.alive || p.ghost_vote).length;
  return `<div class="card stack"><h2>Execute ${esc(nameOf(cur.nominee))}?</h2>
    <p class="small muted">${d.needed} votes needed · ${voted}/${total} have voted${me.alive ? "" : " · a yes spends your ghost vote"}</p>
    ${canVote ? `<div class="vote"><button class="yes ${cur.my_vote === true ? "sel" : ""}" data-act="vote" data-v="1">✋ Yes</button>
      <button class="no ${cur.my_vote === false ? "sel" : ""}" data-act="vote" data-v="0">No</button></div>`
      : `<p class="muted">You have no vote left.</p>`}</div>`;
}

function almanacView() {
  if (!almanac) return `<div class="card">Loading...</div>`;
  const groups = ["townsfolk", "outsider", "minion", "demon"];
  return groups.map(t => `<div class="card"><h3>${t === "townsfolk" ? "Townsfolk" : t[0].toUpperCase() + t.slice(1) + "s"}</h3>
    ${almanac.roles.filter(r => r.type === t).map(r => `<div class="alm"><b class="tag-${r.team}">${esc(r.name)}</b>
    <span>${esc(r.ability)}</span>${wikiDetails(r.id)}</div>`).join("")}</div>`).join("");
}

function logView() {
  return `<div class="card"><h3>Town log</h3><ul class="log">${[...S.public_log].reverse().map(e =>
    `<li><span class="lbl">${esc(e.label)}</span>${esc(e.text)}</li>`).join("")}</ul></div>`;
}

function hostView() {
  const h = S.host, g = S.game;
  const next = { night: "End the night stage now", day: "Open nominations", nominations: "Close nominations and end the day",
                 defense: "Open the vote", vote: "Close the vote" }[g.phase];
  const set = (k, l) => `<label class="row"><span class="grow">${l}</span>
    <input type="number" data-setting="${k}" value="${h.settings[k]}" step="${k === "misregister" || k === "mayor_bounce" ? 0.05 : 5}"></label>`;
  return `<div class="card read"><h3>Read aloud</h3><ul class="log script">${[...h.script].reverse().slice(0, 8).map(e =>
      `<li><span class="lbl">${esc(e.label)}</span>${esc(e.text)}</li>`).join("")}</ul>
    <p class="small muted">You know no more than the other players. These lines contain only public facts.</p></div>
    <div class="card stack"><h3>Timer</h3><div class="row">
      ${g.paused ? `<button class="primary" data-act="resume">Resume</button>` : `<button data-act="pause">Pause</button>`}
      <button data-act="addtime" data-v="-30">−30 s</button><button data-act="addtime" data-v="30">+30 s</button>
      <button data-act="addtime" data-v="120">+2 min</button></div>
      ${next ? `<button class="big" data-act="advance">${next}</button>` : ""}</div>
    <div class="card stack"><h3>Default times (seconds)</h3>
      ${set("discussion", "Day discussion")}${set("nominations", "Nomination floor")}${set("nomination_gap", "Floor after each vote")}
      ${set("defense", "Accusation and defence")}${set("vote", "Vote")}${set("night_min", "Night stage, minimum")}
      ${set("night_max", "Night stage, maximum")}
      <h3>Storyteller chances (0 to 1)</h3>${set("misregister", "Spy/Recluse misregister")}${set("mayor_bounce", "Mayor redirects a kill")}
      <p class="small muted">Changes save when you leave the field. They apply from the next timer.</p></div>
    ${g.phase !== "ended" ? `<button class="danger" data-act="end">End the game now</button>` : ""}`;
}

function endView() {
  const g = S.game;
  return `<div class="card"><div class="winner ${esc(g.winner)}">${esc(g.winner === "nobody" ? "Game ended" : `${g.winner} wins!`)}</div>
    <p style="text-align:center">${esc(g.win_reason)}</p></div>
    <div class="card"><h3>The Grimoire</h3><ul class="log">${(S.grimoire || []).map(x => `<li>
      <b class="tag-${x.role.team}">${esc(x.name)}</b>: ${esc(x.role.name)}${x.shown ? ` <span class="muted small">(thought they were the ${esc(x.shown)})</span>` : ""}
      ${x.alive ? "" : '<span class="muted small">· dead</span>'}</li>`).join("")}</ul>
    <button data-act="leave">Leave and go home</button></div>`;
}

// ---------- storyteller ----------
function roleOptions(sel, filter = () => true) {
  return (almanac?.roles || []).filter(filter).map(r =>
    `<option value="${r.id}" ${r.id === sel ? "selected" : ""}>${esc(r.name)}</option>`).join("");
}

function grimView() {
  const st = S.st, g = S.game;
  if (!st) return `<div class="card">Loading...</div>`;
  const rname = id => almanac?.roles.find(r => r.id === id)?.name ?? id;
  let html = "";
  if (g.phase === "setup") html += `<div class="card read stack"><h2>Check the deal</h2>
    <p>Change any character, the red herring or the bluffs. Players see nothing until you begin.</p>
    <button class="primary big" data-act="begin">Begin the first night</button></div>`;
  if (st.pending.length || g.stage.startsWith("review")) {
    html += `<div class="card read stack"><h2>Night ${g.night}: results to send</h2>
      <p class="small muted">The engine's proposal. Edit any message; empty it to remove it. Deaths so far tonight:
      <b>${st.tonight_deaths.length ? st.tonight_deaths.map(esc).join(", ") : "nobody"}</b>. Use Kill or Revive below to change them.</p>
      ${st.night_choices.length ? `<p class="small">Choices tonight: ${st.night_choices.map(c =>
        `<b>${esc(c.name)}</b> (${esc(c.key)}) → ${esc(c.picks.join(" & "))}`).join(" · ")}</p>` : ""}
      ${st.pending.map(m => m.kind === "info" ? `<label class="stack"><span><b>${esc(m.name)}</b> · ${esc(m.title)}</span>
        <textarea data-pending="${m.pid}" data-index="${m.index}" rows="${Math.max(2, m.lines.length + 1)}">${esc(m.lines.join("\n"))}</textarea></label>`
        : `<p><b>${esc(m.name)}</b> · ${esc(m.title)}: <span class="muted">${esc(m.text)}</span></p>`).join("")}
      <div class="row"><select id="addto" class="grow">${st.grimoire.map(p => `<option value="${p.id}">${esc(p.name)}</option>`).join("")}</select>
        <button data-act="addpending">Add a message</button></div>
      <button class="primary big" data-act="sendpending">${g.stage === "review" ? "Send to players" : "Send and start the day"}</button></div>`;
  }
  if (st.requests.length) html += `<div class="card read stack"><h3>Private requests</h3>${st.requests.map(r => `<div class="stack">
    <p><b>${esc(r.name)}</b> (${esc(r.kind)}, ${esc(r.label)}) ${esc(r.text)}</p>
    <textarea id="req-${r.id}" rows="2" placeholder="Your private answer"></textarea>
    <button data-act="stanswer" data-id="${r.id}">Send answer</button></div>`).join("")}</div>`;
  if (g.phase === "night" && st.choices.length) {
    html += `<div class="card"><h3>Night ${g.night} · stage ${esc(g.stage)}</h3><ul class="log">${st.choices.map(c => `<li>
      <b>${esc(c.name)}</b> ${c.done ? "✓" : '<span class="muted">…</span>'}
      ${c.decoy ? '<span class="muted small">decoy task</span>' : c.tasks.map(t => `<div class="small">${esc(t.title)}:
        ${t.kind === "choose" ? (t.answer ? `<b>${esc(t.answer)}</b>` : '<span class="muted">choosing</span>') : esc(t.lines.join(" "))}</div>`).join("")}
      </li>`).join("")}</ul></div>`;
  }
  html += `<div class="card"><h3>Grimoire</h3><ul class="log">${st.grimoire.map(p => `<li class="stack">
    <div class="row"><b class="grow tag-${p.team}">${p.seat + 1}. ${esc(p.name)}${p.alive ? "" : " · dead"}${!p.alive && p.ghost_vote ? " ●" : ""}</b>
      ${p.alive ? `<button class="danger" data-act="stkill" data-pid="${p.id}">Kill</button>` : `<button data-act="strevive" data-pid="${p.id}">Revive</button>`}
      <button data-act="stmsg" data-pid="${p.id}">Message</button></div>
    <div class="row"><select class="grow" data-char="${p.id}">${roleOptions(p.role)}</select>
      ${p.role === "drunk" ? `<select class="grow" data-shown="${p.id}">${roleOptions(p.shown, r => r.type === "townsfolk")}</select>` : ""}</div>
    ${p.role !== p.shown ? `<span class="small muted">Thinks they are the ${esc(rname(p.shown))}</span>` : ""}
    ${p.notes.length ? `<span class="small">${p.notes.map(esc).join(" · ")}</span>` : ""}
    ${["day", "nominations", "defense", "vote"].includes(g.phase) ? `<button class="danger" data-act="stexec" data-pid="${p.id}">Execute now</button>` : ""}</li>`).join("")}</ul></div>`;
  html += `<div class="card"><h3>Status</h3><ul class="log">${st.status.map(x => `<li class="row"><span class="grow">${esc(x.label)}</span>
    ${x.key === "red_herring" ? `<select data-stset="red_herring">${st.grimoire.map(p => `<option value="${p.id}" ${p.name === x.value ? "selected" : ""}>${esc(p.name)}</option>`).join("")}</select>`
    : x.key === "bluffs" ? x.ids.map((b, i) => `<select data-bluff="${i}">${roleOptions(b, r => r.team === "good")}</select>`).join("")
    : `<b>${esc(x.value)}</b>`}</li>`).join("")}</ul></div>`;
  if (!["setup", "ended"].includes(g.phase)) html += `<div class="card row"><button data-act="stwin" data-v="good">Declare good win</button>
    <button data-act="stwin" data-v="evil">Declare evil win</button></div>`;
  return html;
}

// ---------- night ----------
function nightView() {
  const t = S.task;
  if (!t) return `<div class="night"><div class="inner">${forcedActions()}<div class="done"><b>You are done.</b>
    Put your phone face down and wait for dawn.</div></div></div>`;
  let body = "";
  if (t.kind === "choose") {
    const chosen = ui.picks;
    body = `<p>${esc(t.text)}</p><div class="choice">${t.candidates.map(id => `<button class="${chosen.includes(id) ? "sel" : ""}"
      data-act="pick" data-pid="${id}">${esc(nameOf(id))}${id === S.me.id ? " (you)" : ""}</button>`).join("")}</div>
      <p class="small muted">${chosen.length}/${t.pick} chosen</p>
      <button class="primary big" data-act="submit" ${chosen.length === t.pick ? "" : "disabled"}>Confirm</button>
      ${t.allow_none ? `<button class="big" data-act="none">Choose no one</button>` : ""}`;
  } else if (t.kind === "character") {
    body = `<p>${esc(t.text)}</p>${roleSelect(`nt-${t.id}-c`, t.options)}
      <button class="primary big" data-act="submitchar">Confirm</button>
      ${t.allow_none ? `<button class="big" data-act="none">Choose no one</button>` : ""}`;
  } else if (t.kind === "player_character") {
    body = `<p>${esc(t.text)}</p><div class="stack">${playerSelect(`nt-${t.id}-p`, t.candidates)}${roleSelect(`nt-${t.id}-c`, t.options)}</div>
      <button class="primary big" data-act="submitpc">Confirm</button>`;
  } else if (t.kind === "decoy") {
    body = `<p>${esc(t.text)}</p><div class="choice">${t.options.map(o =>
      `<button data-act="decoy" data-v="${esc(o)}">${esc(o)}</button>`).join("")}</div>`;
  } else {
    body = `<div class="lines">${t.lines.map(l => `<p>${esc(l)}</p>`).join("")}</div>
      <p class="small muted">This is also saved in your notebook.</p>
      <button class="primary big" data-act="ack">Got it</button>`;
  }
  return `<div class="night"><div class="inner">${forcedActions()}<h3>${esc(S.game.label)}</h3><h2>${esc(t.title)}</h2>${body}</div></div>`;
}

// ---------- actions ----------
app.addEventListener("click", async ev => {
  const b = ev.target.closest("[data-act]");
  if (!b || b.disabled) return;
  const d = b.dataset, act = d.act;
  try {
    switch (act) {
      case "host": case "joincode": case "join": {
        const name = document.getElementById("name")?.value.trim();
        if (!name) { toast("Enter your name first."); document.getElementById("name")?.focus(); return; }
        let r;
        if (act === "host") r = await api("/api/games", { name });
        else {
          const code = act === "join" ? d.code : document.getElementById("code").value.trim().toUpperCase();
          if (!code) return toast("Enter the game code.");
          r = await api(`/api/games/${code}/join`, { name });
        }
        session.set({ code: r.code, token: r.token });
        connect(); return;
      }
      case "leave":
        if (!confirm("Leave this game on this device?")) return;
        session.clear(); S = null; ws?.close(); render(); return;
      case "seat": send({ type: "seat", seat: +d.seat }); return;
      case "unseat": send({ type: "seat", seat: null }); return;
      case "begin": if (confirm("Reveal characters and begin the first night?")) send({ type: "begin" }); return;
      case "sendpending": send({ type: "send_pending" }); return;
      case "addpending": {
        const pid = document.getElementById("addto").value, text = prompt(`Message for ${nameOf(pid)}:`);
        if (text) send({ type: "add_pending", player: pid, text }); return;
      }
      case "stkill": if (confirm(`Kill ${nameOf(d.pid)}?`)) send({ type: "st_kill", player: d.pid }); return;
      case "strevive": send({ type: "st_revive", player: d.pid }); return;
      case "stmsg": { const text = prompt(`Private message for ${nameOf(d.pid)}:`); if (text) send({ type: "st_message", player: d.pid, text }); return; }
      case "stwin": if (confirm(`Declare that ${d.v} wins?`)) send({ type: "st_win", team: d.v }); return;
      case "pref": {
        if (d.k === "mode") { send({ type: "mode", mode: d.v }); return; }
        if (d.k === "edition") { send({ type: "edition", edition: d.v }); return; }
        const p = { ...S.me.prefs, [d.k]: d.v };
        send({ type: "prefs", team: p.team, style: p.style }); return;
      }
      case "kick": if (confirm(`Remove ${nameOf(d.pid)}?`)) send({ type: "kick", player: d.pid }); return;
      case "shape":
        if (d.v === "grid") { ui.grid = null; ui.shapeDraft = "grid"; render(); return; }
        ui.shapeDraft = null;
        send({ type: "room", shape: d.v, seats: S.room.seats || Math.max(S.players.length, 8) }); return;
      case "seats": send({ type: "room", shape: S.room.shape, seats: S.room.seats + +d.d }); return;
      case "gdim": {
        const G = ui.grid; G[d.k] = Math.max(1, Math.min(12, G[d.k] + +d.d));
        G.cells = G.cells.filter(([y, x]) => y < G.rows && x < G.cols); render(); return;
      }
      case "cell": {
        const G = ui.grid, y = +d.y, x = +d.x;
        const i = G.cells.findIndex(c => c[0] === y && c[1] === x);
        if (i >= 0) G.cells.splice(i, 1); else G.cells.push([y, x]);
        render(); return;
      }
      case "gclear": ui.grid.cells = []; render(); return;
      case "gapply": ui.shapeDraft = null; send({ type: "room", shape: "grid", rows: ui.grid.rows, cols: ui.grid.cols, cells: ui.grid.cells }); return;
      case "start": if (confirm("Start the game now? Nobody can join after this.")) send({ type: "start" }); return;
      case "tab":
        ui.tab = d.v;
        if (d.v === "me") { ui.logBadge = false; ui.lastLog = S.me.log.length; }
        render(); window.scrollTo(0, 0); return;
      case "player": {
        const pid = d.pid; if (!pid) return;
        if (S.game.phase === "nominations" && S.me.alive && !S.day.nominators.includes(S.me.id)) {
          if (S.day.nominees.includes(pid)) return toast(`${nameOf(pid)} was already nominated today.`);
          ui.nominate = pid; render();
        }
        return;
      }
      case "nominate-ok": send({ type: "nominate", target: ui.nominate }); ui.nominate = null; return;
      case "nominate-cancel": ui.nominate = null; render(); return;
      case "dayact": {
        const payload = dayPayload(d.key, d.kind);
        const a = (S.me.day_actions || []).find(x => x.key === d.key);
        if (a?.public && !confirm(`${a.label}: everyone will see this. Go ahead?`)) return;
        send({ type: "day_action", key: d.key, payload }); return;
      }
      case "none": send({ type: "task", task: S.task.id, response: S.task.kind === "choose" ? [] : null }); return;
      case "submitchar": send({ type: "task", task: S.task.id, response: document.getElementById(`nt-${S.task.id}-c`).value }); return;
      case "submitpc": send({ type: "task", task: S.task.id, response: {
        player: document.getElementById(`nt-${S.task.id}-p`).value, character: document.getElementById(`nt-${S.task.id}-c`).value } }); return;
      case "stexec": if (confirm(`Execute ${nameOf(d.pid)} now? This is today's execution and ends the day.`)) send({ type: "st_execute", player: d.pid }); return;
      case "stanswer": {
        const text = document.getElementById(`req-${d.id}`)?.value || "";
        send({ type: "st_answer", request: d.id, text }); return;
      }
      case "vote": send({ type: "vote", yes: d.v === "1" }); return;
      case "pick": {
        const t = S.task, i = ui.picks.indexOf(d.pid);
        if (i >= 0) ui.picks.splice(i, 1);
        else { if (ui.picks.length >= t.pick) ui.picks.shift(); ui.picks.push(d.pid); }
        render(); return;
      }
      case "submit": send({ type: "task", task: S.task.id, response: ui.picks }); return;
      case "decoy": send({ type: "task", task: S.task.id, response: d.v }); return;
      case "ack": send({ type: "task", task: S.task.id, response: true }); return;
      case "pause": send({ type: "pause" }); return;
      case "resume": send({ type: "resume" }); return;
      case "addtime": send({ type: "add_time", seconds: +d.v }); return;
      case "advance": if (confirm("Move on now?")) send({ type: "advance" }); return;
      case "end": if (confirm("End the game for everyone? This shows the Grimoire.")) send({ type: "end" }); return;
    }
  } catch (e) { toast(e.message); }
});
app.addEventListener("change", ev => {
  const el = ev.target, d = el.dataset;
  if (el.id && (el.id.startsWith("da-") || el.id.startsWith("nt-"))) { ui.form[el.id] = el.value; render(); }
  if (d.setting) send({ type: "setting", key: d.setting, value: +el.value });
  if (d.char) {
    const p = S.st.grimoire.find(x => x.id === d.char);
    send({ type: "set_character", player: d.char, role: el.value, shown: el.value === "drunk" ? (p.role === "drunk" ? p.shown : "washerwoman") : null });
  }
  if (d.shown) send({ type: "set_character", player: d.shown, role: "drunk", shown: el.value });
  if (d.stset) send({ type: "st_set", key: d.stset, value: el.value });
  if (d.bluff != null) {
    const ids = [...S.st.status.find(x => x.key === "bluffs").ids]; ids[+d.bluff] = el.value;
    send({ type: "st_set", key: "bluffs", value: ids });
  }
  if (d.pending) send({ type: "edit_pending", player: d.pending, index: +d.index, lines: el.value.split("\n") });
});
app.addEventListener("keydown", ev => {
  if (ev.key === "Enter" && ev.target.id === "code") document.querySelector('[data-act="joincode"]')?.click();
});

connect();
render();
