"use strict";
// Clocktower Automod browser client. The server sends a personal view;
// this file only renders it and sends the player's actions back.

const app = document.getElementById("app");
const toastEl = document.getElementById("toast");
let S = null;               // latest state from the server
let ws = null, wsTries = 0, wsOpen = false;
let almanac = null;
const ui = { tab: "me", picks: [], taskId: null, slayer: false, nominate: null,
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
    ui.nominate = null; ui.slayer = false;
    if (S.game.phase === "vote" && navigator.vibrate) navigator.vibrate([80, 60, 80]);
  }
  if (prev?.game.phase === "lobby" && S.game.phase !== "lobby") { ui.tab = "me"; keepAwake(); }
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
  if (a && app.contains(a) && (a.tagName === "INPUT" || a.tagName === "SELECT")) {
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
    html += ({ me: meView, town: townView, almanac: almanacView, log: logView, host: hostView }[ui.tab] || meView)();
    html += tabsView();
    if (g.phase === "night") html += nightView();
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
  html += `<div class="card"><h3>Seats</h3><p class="muted small">Tap an empty seat to sit there. Seats run clockwise:
    your neighbours matter.</p>${seatMap({ lobby: true, act: "seat" })}
    ${me.seat != null ? `<button data-act="unseat">Leave my seat</button>` : ""}</div>`;
  html += `<div class="card stack"><h3>Your preferences</h3>
    <p class="small muted">The deal is random, but it tries to give you what you ask for.</p>
    <p>Which team would you like?</p>${seg("team", [["good", "Good"], ["evil", "Evil"], ["any", "No preference"]], me.prefs.team)}
    <p>How do you want to play?</p>${seg("style", [["chill", "Chill"], ["think", "Thinking"], ["any", "No preference"]], me.prefs.style)}
    <p class="small ${me.ready ? "" : "muted"}">${me.ready ? "✓ Saved." : "Tap your choices to save them."}</p></div>`;
  html += `<div class="card"><h3>Players (${S.players.length})</h3><ul class="log">${S.players.map(p => `<li class="row">
    <span class="grow">${esc(p.name)}${p.is_host ? " ★ host" : ""} ${p.seat != null ? `<span class="muted small">seat ${p.seat + 1}</span>` : '<span class="muted small">not seated</span>'}
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
  const n = S.players.length;
  const ok = n >= g.min_players && n <= g.max_players && seated === n;
  html += `<button class="primary big" data-act="start" ${ok ? "" : "disabled"}>Start the game</button>
    <p class="small muted">${n < g.min_players ? `Need at least ${g.min_players} players.` :
      n > g.max_players ? `At most ${g.max_players} players.` : seated < n ? "Everyone must take a seat." :
      "Everyone gets a character when you start."}</p></div>`;
  return html;
}

// ---------- game tabs ----------
function tabsView() {
  const tabs = [["me", "Me"], ["town", "Town"], ["almanac", "Characters"], ["log", "Log"]];
  if (S.me.is_host) tabs.push(["host", "Host"]);
  return `<nav class="tabs">${tabs.map(([k, l]) => `<button class="${ui.tab === k ? "on" : ""}" data-act="tab" data-v="${k}">${l}${
    k === "me" && ui.logBadge ? '<span class="badge"></span>' : ""}${
    k === "town" && ["nominations", "vote", "defense"].includes(S.game.phase) && ui.tab !== "town" ? '<span class="badge"></span>' : ""}</button>`).join("")}</nav>`;
}

function roleCard(r) {
  return `<div class="card role ${r.team}"><div class="type">${esc(r.type)} · <span class="tag-${r.team}">${r.team}</span></div>
    <h2>${esc(r.name)}</h2><p>${esc(r.ability)}</p>${r.tip ? `<p class="small muted">${esc(r.tip)}</p>` : ""}</div>`;
}

function meView() {
  const me = S.me;
  let html = me.role ? roleCard(me.role) : "";
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
  if (g.phase === "vote" && d.current) html += voteCard();
  if (g.phase === "defense" && d.current)
    html += `<div class="card"><h2>${esc(nameOf(d.current.nominator))} nominates ${esc(nameOf(d.current.nominee))}</h2>
      <p>Accusation, then defence. The vote opens when the timer ends.</p></div>`;
  if (d.block) html += `<div class="card"><b>${esc(nameOf(d.block.pid))}</b> is about to die with ${d.block.votes} votes.</div>`;
  if (g.phase === "nominations") {
    const canNom = me.alive && !d.nominators.includes(me.id);
    html += `<div class="card stack"><h3>Nominate</h3>${canNom ? (ui.nominate ?
      `<p>Nominate <b>${esc(nameOf(ui.nominate))}</b>?</p><div class="row"><button class="primary" data-act="nominate-ok">Yes, nominate</button>
       <button data-act="nominate-cancel">Cancel</button></div>` :
      `<p>Tap a player on the map to nominate them.</p>`) :
      `<p class="muted">${me.alive ? "You have already nominated today." : "Dead players cannot nominate."}</p>`}
      ${d.nominees.length ? `<p class="small muted">Already nominated today: ${d.nominees.map(nameOf).map(esc).join(", ")}</p>` : ""}</div>`;
  }
  if (["day", "nominations"].includes(g.phase) && me.alive && !me.slayer_claimed) {
    html += `<div class="card stack"><h3>Slayer shot</h3>${ui.slayer ?
      `<p>Tap the player you shoot. Everyone sees this.</p><button data-act="slayer-cancel">Cancel</button>` :
      `<p class="small muted">Anyone may claim to be the Slayer. Only the real Slayer's shot can kill.</p>
       <button data-act="slayer">Claim a Slayer shot</button>`}</div>`;
  }
  if (d.history.length) html += `<div class="card"><h3>Votes today</h3><ul class="log">${d.history.map(h =>
    `<li>${esc(nameOf(h.nominator))} → ${esc(nameOf(h.nominee))}: <b>${h.votes}</b>
     <span class="small muted">${h.yes.map(nameOf).map(esc).join(", ")}</span></li>`).join("")}</ul></div>`;
  return html;
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
    <span>${esc(r.ability)}</span></div>`).join("")}</div>`).join("");
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

// ---------- night ----------
function nightView() {
  const t = S.task;
  if (!t) return `<div class="night"><div class="inner done"><b>You are done.</b>
    Put your phone face down and wait for dawn.</div></div>`;
  let body = "";
  if (t.kind === "choose") {
    const chosen = ui.picks;
    body = `<p>${esc(t.text)}</p><div class="choice">${t.candidates.map(id => `<button class="${chosen.includes(id) ? "sel" : ""}"
      data-act="pick" data-pid="${id}">${esc(nameOf(id))}${id === S.me.id ? " (you)" : ""}</button>`).join("")}</div>
      <p class="small muted">${chosen.length}/${t.pick} chosen</p>
      <button class="primary big" data-act="submit" ${chosen.length === t.pick ? "" : "disabled"}>Confirm</button>`;
  } else if (t.kind === "decoy") {
    body = `<p>${esc(t.text)}</p><div class="choice">${t.options.map(o =>
      `<button data-act="decoy" data-v="${esc(o)}">${esc(o)}</button>`).join("")}</div>`;
  } else {
    body = `<div class="lines">${t.lines.map(l => `<p>${esc(l)}</p>`).join("")}</div>
      <p class="small muted">This is also saved in your notebook.</p>
      <button class="primary big" data-act="ack">Got it</button>`;
  }
  return `<div class="night"><div class="inner"><h3>${esc(S.game.label)}</h3><h2>${esc(t.title)}</h2>${body}</div></div>`;
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
      case "pref": {
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
        if (ui.slayer) {
          if (confirm(`Claim a Slayer shot at ${nameOf(pid)}? Everyone will see it.`)) send({ type: "slayer", target: pid });
          ui.slayer = false; render(); return;
        }
        if (S.game.phase === "nominations" && S.me.alive && !S.day.nominators.includes(S.me.id)) {
          if (S.day.nominees.includes(pid)) return toast(`${nameOf(pid)} was already nominated today.`);
          ui.nominate = pid; render();
        }
        return;
      }
      case "nominate-ok": send({ type: "nominate", target: ui.nominate }); ui.nominate = null; return;
      case "nominate-cancel": ui.nominate = null; render(); return;
      case "slayer": ui.slayer = true; render(); toast("Tap the player you shoot on the map.", "info"); return;
      case "slayer-cancel": ui.slayer = false; render(); return;
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
  const el = ev.target;
  if (el.dataset.setting) send({ type: "setting", key: el.dataset.setting, value: +el.value });
});
app.addEventListener("keydown", ev => {
  if (ev.key === "Enter" && ev.target.id === "code") document.querySelector('[data-act="joincode"]')?.click();
});

connect();
render();
