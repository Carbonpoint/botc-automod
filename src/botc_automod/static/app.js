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
  set(v) { try { localStorage.setItem("botc", JSON.stringify(v)); } catch {} tokens.add(v.token); },
  clear() { try { localStorage.removeItem("botc"); } catch {} },
};
// Every player token this browser has held. After a pause the server knows
// the player by it, so they go straight back to their seat.
const tokens = {
  all() { try { return JSON.parse(localStorage.getItem("botc-tokens") || "[]"); } catch { return []; } },
  add(t) { try { localStorage.setItem("botc-tokens", JSON.stringify([t, ...tokens.all().filter(x => x !== t)].slice(0, 30))); } catch {} },
};
const ICON = {
  trash: `<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/></svg>`,
  star: `<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" d="M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z"/></svg>`,
  folder: `<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" d="M3 6.5A1.5 1.5 0 0 1 4.5 5H9l2 2.5h8.5A1.5 1.5 0 0 1 21 9v9.5a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 18.5z"/></svg>`,
};
// A pop-up that asks a yes/no question. Resolves true for yes.
function ask(question, yes = "Yes", no = "No") {
  return new Promise(done => {
    const el = document.createElement("div");
    el.className = "modal";
    el.innerHTML = `<div class="box" role="dialog" aria-modal="true"><p>${esc(question)}</p>
      <div class="row"><button class="grow" data-a="0">${esc(no)}</button><button class="primary grow" data-a="1">${esc(yes)}</button></div></div>`;
    el.addEventListener("click", ev => {
      const b = ev.target.closest("[data-a]");
      if (!b && ev.target !== el) return;
      el.remove(); done(b?.dataset.a === "1");
    });
    document.body.appendChild(el);
    el.querySelector('[data-a="0"]').focus();
  });
}
// Save a response from the server as a file on this device.
async function download(r) {
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || "Download failed");
  const name = /filename="([^"]+)"/.exec(r.headers.get("Content-Disposition") || "")?.[1] || "game.md";
  const a = document.createElement("a");
  a.href = URL.createObjectURL(await r.blob()); a.download = name;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 5000);
}
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

// ---------- sound and vibration ----------
// Short tones made in the browser (no audio files), and phone vibration.
// Only public moments make a sound: every phone hears the same thing at the
// same time. Night tasks only vibrate, and every player gets a night task.
const feel = {
  get() { const d = { sound: true, vibrate: true, popups: true, dmBuzz: false };
          try { return { ...d, ...JSON.parse(localStorage.getItem("botc-feel") || "{}") }; } catch { return d; } },
  set(k, v) { try { localStorage.setItem("botc-feel", JSON.stringify({ ...feel.get(), [k]: v })); } catch {} },
};
let audio = null;
function unlockAudio() {   // browsers allow sound only after the player touches the page
  try {
    audio = audio || new (window.AudioContext || window.webkitAudioContext)();
    if (audio.state === "suspended") audio.resume();
  } catch {}
}
document.addEventListener("pointerdown", unlockAudio, { capture: true });
// Each sound: a list of [frequency Hz, start s, length s, wave, volume].
const SOUNDS = {
  night:       [[392, 0, .5, "sine", .25], [311, .35, .6, "sine", .25], [262, .8, 1.1, "sine", .25]],
  dawn:        [[523, 0, .35, "triangle", .2], [659, .2, .35, "triangle", .2], [784, .4, .7, "triangle", .2]],
  narrator:    [[784, 0, .15, "triangle", .25], [988, .15, .15, "triangle", .25], [1319, .3, .5, "triangle", .25]],
  day:         [[659, 0, .25, "sine", .2], [880, .18, .5, "sine", .2]],
  nominations: [[440, 0, .12, "square", .08], [554, .14, .12, "square", .08], [659, .28, .3, "square", .08]],
  nominated:   [[196, 0, .12, "square", .12], [196, .18, .12, "square", .12]],
  vote:        [[880, 0, .1, "square", .08], [880, .15, .1, "square", .08], [1175, .3, .3, "square", .08]],
  warn:        [[988, 0, .12, "sine", .2], [988, .2, .12, "sine", .2]],
  tick:        [[1400, 0, .05, "square", .06]],
  end:         [[523, 0, 1.2, "sine", .15], [659, .1, 1.1, "sine", .15], [784, .2, 1, "sine", .15]],
  chat:        [[1047, 0, .08, "sine", .12], [1319, .07, .12, "sine", .12]],
};
const BUZZ = { night: [300], dawn: [80, 60, 80], narrator: [120, 60, 120, 60, 400], nominations: [60],
               nominated: [150], vote: [80, 60, 80], warn: [200], tick: [30], end: [400], chat: [40], dm: [40, 40, 40] };
function cue(name) {
  const f = feel.get();
  if (f.vibrate && BUZZ[name] && navigator.vibrate) navigator.vibrate(BUZZ[name]);
  if (!f.sound || !audio || audio.state !== "running") return;
  const t0 = audio.currentTime + .02;
  for (const [hz, at, len, wave, vol] of SOUNDS[name] || []) {
    const o = audio.createOscillator(), g = audio.createGain();
    o.type = wave; o.frequency.value = hz;
    g.gain.setValueAtTime(0, t0 + at);
    g.gain.linearRampToValueAtTime(vol, t0 + at + .01);
    g.gain.exponentialRampToValueAtTime(.001, t0 + at + len);
    o.connect(g).connect(audio.destination);
    o.start(t0 + at); o.stop(t0 + at + len + .05);
  }
}
// Warnings as a day timer runs out: 30 s, 10 s, then a tick each second of the last 5 of a vote.
function timerCue(prev, now) {
  if (!S || prev == null || now == null || now >= prev || S.game.paused) return;
  const ph = S.game.phase;
  if (!["day", "nominations", "defense", "vote"].includes(ph) || S.game.stage === "narration") return;
  if ((prev > 30 && now <= 30 && ph !== "vote" && ph !== "defense") || (prev > 10 && now <= 10)) cue("warn");
  else if (ph === "vote" && now <= 5 && now >= 1) cue("tick");
}
function feelCard() {
  const f = feel.get(), b = (k, on) => `<button class="${f[k] === on ? "sel" : ""}" data-act="feel" data-k="${k}" data-v="${on ? 1 : 0}">${on ? "On" : "Off"}</button>`;
  const row = (k, label) => `<div class="row"><span class="grow">${label}</span><div class="seg">${b(k, true)}${b(k, false)}</div></div>`;
  return `<div class="card stack"><h3>On this phone</h3>
    ${row("sound", "Sounds")}${row("vibrate", "Vibration")}${row("popups", "Chat pop-ups")}${row("dmBuzz", "Vibrate for private messages")}
    <p class="small muted">Sounds mark night, dawn, nominations, votes and group messages, and warn when time runs low.
      Private messages only show a quiet "new message" pop-up. iPhones do not vibrate from a web page,
      and their silent switch mutes the sounds.</p></div>`;
}
// A pop-up at the top of the screen. Tapping it opens the chat.
function popup(text, thread) {
  let el = document.getElementById("popup");
  if (!el) { el = document.createElement("button"); el.id = "popup"; document.body.appendChild(el);
             el.addEventListener("click", () => { el.hidden = true; ui.tab = "chat"; ui.thread = el.dataset.thread || ""; render(); }); }
  el.textContent = text; el.dataset.thread = thread; el.hidden = false;
  clearTimeout(popup.t); popup.t = setTimeout(() => (el.hidden = true), 4000);
}
// New messages since the last state: pop-ups, sound and vibration by this phone's settings.
function chatCues(prev) {
  const msgs = S.chat || [];
  const top = msgs.length ? msgs[msgs.length - 1].id : 0;
  if (!prev) {   // a fresh page: what is already there counts as read
    ui.chatTop = top; ui.read = {};
    for (const m of msgs) ui.read[threadOf(m)] = m.id;
    return;
  }
  const f = feel.get();
  for (const m of msgs.filter(m => m.id > (ui.chatTop || 0) && m.from !== S.me.id)) {
    const thread = threadOf(m);
    if (ui.tab === "chat" && (ui.thread || "") === thread) continue;   // already on screen
    if (!m.to) {
      if (f.popups) popup(`${sender(m)}: ${m.text}`, "");
      cue("chat");
    } else {
      if (f.popups) popup("New private message", thread);
      if (f.dmBuzz && navigator.vibrate) navigator.vibrate(BUZZ.dm);
    }
  }
  ui.chatTop = top;
}

// ---------- connection ----------
function connect() {
  const s = session.get();
  if (!s) return render();
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws/${s.code}?token=${encodeURIComponent(s.token)}`);
  ws.onopen = () => { wsOpen = true; wsTries = 0; render(); };
  ws.onmessage = ev => {
    const m = JSON.parse(ev.data);
    if (m.type === "state") { ui.tipBusy = false; onState(m.state); }
    else if (m.type === "timer") { if (S) { const was = S.game.timer; S.game.timer = m.timer; S.game.paused = m.paused; drawTimer(); timerCue(was, m.timer); } }
    else if (m.type === "error") { ui.artistBusy = false; ui.tipBusy = false; toast(m.message); render(); }
    else if (m.type === "info") { toast(m.message, "info"); }
    else if (m.type === "artist_preview") { ui.artistBusy = false; ui.artistPreview = m; render(); }
    else if (m.type === "gone") { session.clear(); S = null; toast("That game no longer exists."); render(); }
    else if (m.type === "paused") { session.clear(); S = null; toast("The host paused the game. It is in Archive, Paused.", "info"); render(); }
  };
  ws.onclose = ev => {
    wsOpen = false;
    if (ev.code === 4004 || ev.code === 4001 || ev.code === 4005) { session.clear(); S = null; render(); return; }
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
    if (navigator.vibrate && feel.get().vibrate) navigator.vibrate(120);
  }
  if (prev && prev.game.phase !== S.game.phase) ui.nominate = null;
  if (prev) {
    const was = prev.game.phase + "/" + prev.game.stage, now = S.game.phase + "/" + S.game.stage;
    if (was !== now) {
      const ph = S.game.phase;
      if (ph === "night" && prev.game.phase !== "night") cue("night");
      else if (ph === "day" && S.game.stage === "narration") cue(S.narration?.narrator === S.me.id ? "narrator" : "dawn");
      else if (ph === "day" && prev.game.phase !== "day") cue("dawn");
      else if (ph === "day") cue("day");
      else if (ph === "nominations" && prev.game.phase !== "nominations") cue("nominations");
      else if (ph === "defense") cue("nominated");
      else if (ph === "vote") cue("vote");
      else if (ph === "ended") cue("end");
    }
  }
  if (prev?.game.phase === "lobby" && S.game.phase !== "lobby") { ui.tab = S.me.storyteller ? "grim" : "me"; keepAwake(); }
  if (!prev && S.me.storyteller && ui.tab === "me") ui.tab = "grim";
  chatCues(prev);
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
  if (!session.get()) {
    if (ui.view === "archive") { app.innerHTML = archiveView(); return; }
    if (ui.view === "arcade") { Arcade.render(); return; }
    app.innerHTML = homeView(); loadGames(); return;
  }
  if (!S) { app.innerHTML = `<div class="card">Connecting...</div>`; return; }
  const g = S.game;
  const overlay = (g.phase === "night" && !S.me.storyteller) || g.stage === "narration";  // those screens show their own copy
  let html = topBar() + (overlay ? "" : rejoinBanner());
  if (g.phase === "lobby") html += lobbyView();
  else {
    if (g.phase === "ended") html += endView();
    html += ({ me: meView, grim: grimView, town: townView, almanac: almanacView, log: logView, host: hostView,
               chat: chatView }[ui.tab] || meView)();
    html += tabsView();
    if (g.phase === "night" && !S.me.storyteller) html += nightView();
    if (g.phase === "day" && g.stage === "narration" && S.narration) html += dawnView();
  }
  app.innerHTML = html;
  const box = document.getElementById("msgs");
  if (box) box.scrollTop = box.scrollHeight;
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
    <h3><label for="name">Your name</label></h3>
    <input id="name" maxlength="24" autocomplete="nickname" placeholder="Name shown to the table" value="${esc(ui.name || "")}">
  </div>
  <div class="card stack">
    <h3><label for="code">Join a game</label></h3>
    <input id="code" maxlength="4" placeholder="Code, e.g. KQTR" autocapitalize="characters" style="text-transform:uppercase">
    <div id="games" class="stack"></div>
  </div>
  <div class="home-actions">
    <button class="primary join" data-act="joincode">Join</button>
    <button class="big" data-act="host">Host a new game</button>
    <div class="row home-links">
      <button class="linkish" data-act="archive">${ICON.folder}<span>Archive</span></button>
      <button class="linkish" data-act="arcade">${ICON.star}<span>Karma arcade</span></button></div>
  </div>`;
}
async function loadGames() {
  try {
    const list = await api("/api/games");
    const el = document.getElementById("games");
    if (!el) return;
    const players = g => `${g.players} player${g.players === 1 ? "" : "s"}`;
    const open = list.filter(g => g.phase === "lobby"), playing = list.filter(g => g.phase !== "lobby");
    el.innerHTML = (open.length ? open.map(g => `<div class="gamerow">
      <button class="big grow" data-act="join" data-code="${esc(g.code)}">
        Join ${esc(g.host)}'s game <span class="code">${esc(g.code)}</span>
        <span class="muted small">· ${players(g)}</span></button>
      <button class="icon" data-act="delgame" data-code="${esc(g.code)}" data-host="${esc(g.host)}"
        aria-label="Delete ${esc(g.host)}'s game" title="Delete this game">${ICON.trash}</button></div>`).join("")
      : `<p class="muted small">No open games on this server yet.</p>`)
      + (playing.length ? `<p class="muted small">Games in play. Rejoin with the name you played with.</p>` + playing.map(g =>
      `<button class="big" data-act="join" data-code="${esc(g.code)}">
        Rejoin ${esc(g.host)}'s game <span class="code">${esc(g.code)}</span>
        <span class="muted small">· ${esc(g.where)} · ${players(g)}</span></button>`).join("") : "");
  } catch {}
}
setInterval(() => { if (!session.get() && !ui.view) loadGames(); }, 4000);

// ---------- archive ----------
async function openArchive() {
  ui.view = "archive"; ui.archive = null; render();
  try { ui.archive = await api("/api/archive"); } catch (e) { toast(e.message); ui.archive = { completed: [], paused: [], path: "" }; }
  render();
}
function archiveView() {
  const a = ui.archive, sub = ui.archiveTab || "completed";
  const back = `<button data-act="home">← Back</button>`;
  if (!a) return `<div class="archive-top">${back}<h1>Archive</h1></div><div class="card">Loading...</div>`;
  const rows = a[sub];
  const row = f => `<div class="card stack">
      <div><b>${esc(f.edition)}</b> <span class="code">${esc(f.code)}</span></div>
      <div class="muted small">${esc(f.started)} · host ${esc(f.host)} · ${esc(f.players)} players</div>
      <div>${sub === "completed" ? esc(f.winner === "nobody" ? "Nobody won" : `${f.winner || "?"} won`.replace(/^./, c => c.toUpperCase()))
                                 : `Paused at ${esc(f.where)}`}</div>
      <div class="row">
        ${sub === "paused" ? `<button class="primary" data-act="resumegame" data-file="${esc(f.file)}" data-host="${esc(f.host)}">Resume</button>` : ""}
        <button data-act="exportfile" data-file="${esc(f.file)}">Export as Markdown</button></div></div>`;
  return `<div class="archive-top">${back}<h1>Archive</h1></div>
    <div class="seg">
      <button class="${sub === "completed" ? "sel" : ""}" data-act="archivetab" data-v="completed">${ICON.folder} Completed (${a.completed.length})</button>
      <button class="${sub === "paused" ? "sel" : ""}" data-act="archivetab" data-v="paused">${ICON.folder} Paused (${a.paused.length})</button></div>
    ${rows.length ? rows.map(row).join("") : `<p class="muted">No ${sub} games.</p>`}
    <div class="card stack"><h3>Import a game</h3>
      <p class="small">Choose a game file (.md) from another server or from an export. A game in play goes to Paused; a finished game goes to Completed.</p>
      <input type="file" id="importfile" accept=".md,text/markdown,text/plain">
      ${a.path ? `<p class="small muted">The game files on this server are in <span class="path">${esc(a.path)}</span>,
        in the folders running, paused and completed. To move games to another server, copy the .md files
        into the same folders there. A server reads running/ when it starts; paused/ and completed/ show here at once.</p>` : ""}
    </div>`;
}

async function waitForRejoin(code, rid) {
  app.innerHTML = `<div class="card stack" style="margin-top:24px"><h2>Asking to rejoin</h2>
    <p>The game has started, so the host must let you back in. Ask them to look at their phone.</p></div>`;
  for (let i = 0; i < 150; i++) {
    await new Promise(r => setTimeout(r, 2000));
    try {
      const r = await api(`/api/games/${code}/rejoin/${rid}`);
      if (r.status === "approved") { session.set({ code, token: r.token }); toast("Welcome back.", "info"); connect(); return; }
      if (r.status === "denied") { toast("The host said no."); render(); return; }
    } catch (e) { toast(e.message); render(); return; }
  }
  toast("No answer from the host. Try again."); render();
}

function rejoinBanner() {
  return (S.rejoins || []).map(r => `<div class="card read row"><span class="grow"><b>${esc(r.name)}</b> wants to rejoin on a new device.</span>
    <button class="primary" data-act="rejoin" data-id="${r.id}" data-v="1">Let them in</button>
    <button data-act="rejoin" data-id="${r.id}" data-v="0">No</button></div>`).join("");
}

// ---------- lobby ----------
// A live vote on the Town map and in the Grimoire (host option show_votes).
const voteMark = yes => `<span class="vmark" title="${yes ? "Votes to execute" : "Votes no"}">${yes ? "💀" : "😇"}</span>`;
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
      if (p.agent) cls.push("agent");
      else if (!p.connected) cls.push("off");
      if (block && block.pid === p.id) cls.push("block");
      if (cur && cur.nominee === p.id) cls.push("nominee");
    }
    const label = p ? `${p.agent ? "🤖 " : ""}${esc(p.name)}${p.is_host ? " ★" : ""}${!p.alive && p.ghost_vote ? ' <span class="ghost">●</span>' : ""}`
                    : (opts.lobby ? "Sit here" : "");
    const vote = p && cur?.votes && p.id in cur.votes ? voteMark(cur.votes[p.id]) : "";
    const act = opts.act && (p ? opts.act !== "seat" : opts.act === "seat") ? `data-act="${opts.act}" data-seat="${s.index}" data-pid="${p?.id ?? ""}"` : "";
    const w = room.shape === "grid" && room.cols ? `width:${Math.min(22, 72 / room.cols).toFixed(1)}%;` : "";
    return `<button class="${cls.join(" ")}" style="left:${s.x * 100}%;top:${s.y * 100}%;${w}" ${act}>
      <span class="n">${s.index + 1}</span>${label}${vote}</button>`;
  }).join("");
  // One continuous path through the seats in order, with arrows for the direction.
  // In a game it joins occupied seats only; in the lobby it shows the whole order.
  const W = room.shape === "grid" && room.rows ? 100 * room.cols / room.rows : 100, H = 100;
  const pts = layout.filter(s => opts.lobby || bySeat[s.index]).map(s => [s.x * W, s.y * H]);
  let path = "";
  if (pts.length > 1) {
    const segs = pts.map((a, i) => [a, pts[(i + 1) % pts.length]]);
    const arrows = segs.map(([a, b]) => {
      const mx = (a[0] + b[0]) / 2, my = (a[1] + b[1]) / 2, ang = Math.atan2(b[1] - a[1], b[0] - a[0]) * 180 / Math.PI;
      return `<polygon points="-2.4,-2 2.4,0 -2.4,2" transform="translate(${mx.toFixed(1)} ${my.toFixed(1)}) rotate(${ang.toFixed(1)})"/>`;
    }).join("");
    path = `<svg class="path" viewBox="0 0 ${W.toFixed(1)} ${H}" aria-hidden="true">
      <polyline points="${[...pts, pts[0]].map(p => p.map(v => v.toFixed(1)).join(",")).join(" ")}"/>${arrows}</svg>`;
  }
  return `<div class="map ${flat ? "flat" : ""} ${layout.length > 12 ? "dense" : ""}" style="${ratio}">${path}${seats}</div>`;
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
      ${ui.editions ? seg("edition", ui.editions.map(e => [e.id, e.name]), g.edition.id) : ""}</div>
      <div class="card stack"><h3>Theme</h3>
      ${seg("theme", [["default", "Default"], ["jojo", "Jo Jo's Mid-Autumn Festival"]], g.theme.id)}
      <p class="small muted">${g.theme.id === "jojo"
        ? "A rainy, cold fall night at Jo Jo's apartment in Ames, Iowa. The morning stories happen there."
        : "Ravenswood Bluff, the classic Clocktower town. The morning stories happen there."}</p></div>`;
  } else html += `<div class="card"><p>Edition: <b>${esc(g.edition.name)}</b></p>
      <p>Theme: <b>${esc(g.theme.name)}</b></p></div>`;
  if (me.is_host && S.host) {
    const st = S.host.settings, on = k => st[k] ?? (["irl_tasks", "anon_chat"].includes(k) ? 0 : 1), tog = (k, label, help) => `<div class="stack"><p>${label}</p>
      <div class="seg"><button class="${on(k) ? "sel" : ""}" data-act="toggle" data-k="${k}" data-v="1">On</button>
      <button class="${on(k) ? "" : "sel"}" data-act="toggle" data-k="${k}" data-v="0">Off</button></div>
      <p class="small muted">${help}</p></div>`;
    html += `<div class="card stack"><h3>Options</h3>
      ${tog("demon_bluffs", "Demon bluffs in small games", "The Demon always learns 3 good characters that are safe to claim. Off follows the official rule: no evil info with 5 or 6 players.")}
      ${tog("karma", "Karma", "Right answers to the night question earn karma. Chance then favours players with high karma, a little.")}
      ${tog("show_votes", "Show votes on seats", "During a vote, every seat shows its vote as it comes in: 💀 to execute, 😇 for no. Off: votes stay hidden until the vote ends.")}
      ${tog("anon_chat", "Anonymous messages", "Players may send chat messages, to the group or to one player, without their name. Nobody can see who sent them.")}
      ${tog("irl_tasks", "Keyword tasks", "Each day every player gets a secret keyword and must meet another player in person to get theirs. Right keyword: karma +2. Missed: −1. Finding someone else's: +1 for you, −1 for them. Needs karma on.")}
      ${tog("narrator", "Morning narrator", "At dawn a random player, dead or alive, reads a made-up story of how the night's victims died. The day starts when they tap done.")}</div>`
      + helperCard();
  }
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
  html += feelCard();
  html += `<button class="danger" data-act="leave">Leave this game</button>`;
  return html;
}
// The host's helpful narrator controls: who gets tips, and who is learning.
function helperCard() {
  const h = S.host, m = h.settings.helper ?? 0;
  const b = (v, l) => `<button class="${m === v ? "sel" : ""}" data-act="helper" data-v="${v}">${l}</button>`;
  const people = S.players.filter(p => p.seat != null || S.game.phase === "lobby");
  return `<div class="card stack"><h3>Helpful narrator</h3>
    <div class="seg">${b(0, "Off")}${b(1, "Learners")}${b(2, "Everyone")}</div>
    <p class="small muted">Once a day, a player can ask the narrator for a small tip: help with their
      character, a hint from public facts, and someone to talk to.
      Tips never tell who is evil. Good karma makes the "talk to" hint a little better.</p>
    ${m === 1 ? `<p>Tap the players who are learning:</p><div class="choice">${people.map(p =>
      `<button class="${h.learners.includes(p.id) ? "sel" : ""}" data-act="learner" data-pid="${p.id}"
        data-v="${h.learners.includes(p.id) ? 0 : 1}">${esc(p.name)}</button>`).join("")}</div>` : ""}</div>`;
}
// Keyword task: meet a player in person and enter their keyword (keywords.py).
function keywordCard() {
  const k = S.me.irl;
  if (!k) return "";
  const day = ["day", "nominations", "defense", "vote"].includes(S.game.phase) && S.game.stage !== "narration";
  const others = k.players.filter(id => id !== k.target && !k.found.includes(id));
  return `<div class="card stack keyword"><h3>Keyword task</h3>
    <p>Your keyword: <b class="code">${esc(k.word.toUpperCase())}</b>. Tell it only to <b>${esc(nameOf(k.give_to))}</b>, in person.</p>
    ${k.done ? `<p>✓ You got ${esc(nameOf(k.target))}'s keyword.</p>`
      : `<p>Your task: meet <b>${esc(nameOf(k.target))}</b> and get their keyword.</p>`}
    ${!day ? "" : k.left <= 0 ? `<p class="muted">No tries left today.</p>` : k.done
      ? (others.length ? `<p class="small">Know someone else's keyword? Each one you find gives you karma,
          and costs its owner and the player meant to get it.</p>
          <div class="row"><select id="kw-p">${others.map(id => `<option value="${id}">${esc(nameOf(id))}</option>`).join("")}</select>
          <input id="kw-w" class="grow" maxlength="40" placeholder="Their keyword"><button data-act="keyword" data-extra="1">Try</button></div>` : "")
      : `<div class="row"><input id="kw-w" class="grow" maxlength="40" placeholder="${esc(nameOf(k.target))}'s keyword">
          <button class="primary" data-act="keyword">Enter</button></div>`}
    ${day && k.left > 0 ? `<p class="small muted">${k.left} ${k.left === 1 ? "try" : "tries"} left today.</p>` : ""}</div>`;
}

function tipCard() {
  const t = S.me.tip;
  if (!t || !t.on || S.me.seat == null || S.game.phase === "lobby" || S.game.phase === "ended") return "";
  if (!t.can) return `<div class="card"><h3>Helpful narrator</h3><p class="small muted">${
    ["day", "nominations", "defense", "vote"].includes(S.game.phase)
      ? "You have had today's tip. It is in your notebook below." : "The narrator gives tips by day."}</p></div>`;
  return `<div class="card stack"><h3>Helpful narrator</h3>
    <p class="small">Once a day, the narrator can give you a small tip. It goes into your notebook.</p>
    ${t.ask ? `<textarea id="tip-q" rows="2" maxlength="200" placeholder="Your question (optional), e.g. How should I use my info today?"></textarea>` : ""}
    <button class="primary" data-act="tip"${ui.tipBusy ? " disabled" : ""}>${ui.tipBusy ? "The narrator is thinking..." : "Ask the narrator for a tip"}</button></div>`;
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
  const ags = S.players.filter(p => p.agent), empty = S.layout.length - seated;
  html += `</div><div class="card stack"><h3>Agents</h3>
    <p class="small muted">Agents are computer players for empty seats: to play a bigger game, to fill a small group,
      or to test alone. They do their night tasks, nominate, vote and chat.</p>
    <div class="row"><button data-act="addagent" ${empty ? "" : "disabled"}>Add an agent</button>
      <button data-act="fillagents" ${empty ? "" : "disabled"}>Fill ${empty} empty seat${empty === 1 ? "" : "s"}</button></div>
    ${ags.length ? `<div class="choice">${ags.map(p => `<button data-act="kick" data-pid="${p.id}">🤖 ${esc(p.name)} ✕</button>`).join("")}</div>
      <p class="small muted">Tap an agent to remove it.</p>` : ""}</div><div class="card stack">`;
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
  tabs.push(["chat", "Chat"]);
  if (S.me.is_host) tabs.push(["host", "Host"]);
  return `<nav class="tabs${tabs.length > 5 ? " many" : ""}">${tabs.map(([k, l]) => `<button class="${ui.tab === k ? "on" : ""}" data-act="tab" data-v="${k}">${l}${
    k === "me" && ui.logBadge ? '<span class="badge"></span>' : ""}${
    k === "chat" && ui.tab !== "chat" && unread().total ? '<span class="badge"></span>' : ""}${
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
  if (me.bluffs && me.bluffs.length) html += `<div class="card"><h3>Your bluffs</h3>
    <p>These good characters are not in play, so they are safe to claim: <b>${me.bluffs.map(esc).join(", ")}</b>.</p></div>`;
  html += `<div class="card"><p>You are <b>${me.alive ? "alive" : "dead"}</b>.
    ${me.karma != null ? `Karma: <b>${me.karma > 0 ? "+" : ""}${me.karma}</b>.` : ""}
    ${me.alive ? "" : me.ghost_vote ? "You still have your one ghost vote." : "You have used your ghost vote."}</p></div>`;
  html += keywordCard() + tipCard();
  html += `<div class="card"><h3>Your notebook</h3><p class="small muted">Everything the storyteller has told you in private.</p>
    <ul class="log">${[...me.log].reverse().map(e => `<li><span class="lbl">${esc(e.label)}</span>${esc(e.text)}</li>`).join("")}</ul></div>`;
  return html + feelCard();
}

function townView() {
  const g = S.game, d = S.day, me = S.me;
  let html = `<div class="card">${seatMap({ act: "player" })}
    <p class="small muted">★ host · ● ghost vote left · red ring: about to die${d.needed ? ` · ${d.needed} votes needed to execute` : ""}${
      d.current?.votes ? " · 💀 votes to execute · 😇 votes no" : ""}</p></div>`;
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
  if (a.kind === "question" && a.free_text) {
    const pv = ui.artistPreview;
    form = `<textarea id="${id}-text" rows="2" maxlength="300" placeholder="Any yes/no question about this game">${esc(fv(`${id}-text`))}</textarea>
      ${pv ? (pv.ok ? `<div class="read card"><p>I understood: <b>${esc(pv.reading)}</b>?</p>
          <div class="row"><button class="primary" data-act="artistask" data-id="${pv.id}">Ask this</button>
          <button data-act="artistclear">Change it</button></div></div>`
        : `<p class="small">The Storyteller cannot answer that yes or no. Try other words; your ability is not used.</p>`) : ""}`;
    if (S.game.mode === "auto") return `<div class="card stack"><h3>${esc(a.label)}</h3><p class="small muted">${esc(a.help || "")}
      The Storyteller shows you how it reads your question before answering.</p><div class="stack">${form}</div>
      ${pv && pv.ok ? "" : `<button data-act="artistcheck" ${ui.artistBusy ? "disabled" : ""}>${ui.artistBusy ? "Reading…" : "Check my question"}</button>`}</div>`;
  } else if (a.kind === "target") {
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
  if (kind === "question" && document.getElementById(`${id}-text`) && !document.getElementById(`${id}-kind`))
    return { text: val("text") || "" };
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
    <span>${esc(r.ability)}</span>${wikiDetails(r.id)}</div>`).join("")}</div>`).join("")
    + (S.me.annoy ? `<p class="egg"><button data-act="annoy">Annoy Tommy?</button></p>` : "");
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
      ${g.paused ? `<button class="primary" data-act="resume">Resume timer</button>` : `<button data-act="pause">Pause timer</button>`}
      <button data-act="addtime" data-v="-30">−30 s</button><button data-act="addtime" data-v="30">+30 s</button>
      <button data-act="addtime" data-v="120">+2 min</button></div>
      ${next ? `<button class="big" data-act="advance">${next}</button>` : ""}</div>
    <div class="card stack"><h3>Default times (seconds)</h3>
      ${set("discussion", "Day discussion")}${set("nominations", "Nomination floor")}${set("nomination_gap", "Floor after each vote")}
      ${set("defense", "Accusation and defence")}${set("vote", "Vote")}${set("night_min", "Night stage, minimum")}
      ${set("night_max", "Night stage, maximum")}
      <h3>Storyteller chances (0 to 1)</h3>${set("misregister", "Spy/Recluse misregister")}${set("mayor_bounce", "Mayor redirects a kill")}
      <p class="small muted">Changes save when you leave the field. They apply from the next timer.</p></div>
    ${g.phase !== "ended" ? helperCard() : ""}
    ${g.phase !== "ended" ? `<div class="card stack"><h3>Save the game</h3>
      <p class="small muted">The server saves the game after every change, so it survives a crash.
        Export gives you a copy of that file. Pause stops the game for everyone; resume it later from Archive, Paused.</p>
      <div class="row"><button class="grow" data-act="exportgame">Export as Markdown</button>
        <button class="grow" data-act="pausegame">Pause the game</button></div></div>
    <button class="danger" data-act="end">End the game now</button>` : ""}`;
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
    <div class="row"><b class="grow tag-${p.team}">${p.seat + 1}. ${esc(p.name)}${p.alive ? "" : " · dead"}${!p.alive && p.ghost_vote ? " ●" : ""}
      <span class="small muted">karma ${p.karma}</span>${S.day.current?.votes && p.id in S.day.current.votes ? voteMark(S.day.current.votes[p.id]) : ""}</b>
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
  if (!t) {
    const me = S.me, res = me.last_answer;
    const k = me.karma != null && res ? `<p>${res === "right" ? "Right answer: +1 karma." : "Wrong answer: −1 karma."}
      Your karma: <b>${me.karma > 0 ? "+" : ""}${me.karma}</b></p>` : "";
    return `<div class="night"><div class="inner">${rejoinBanner()}${forcedActions()}<div class="done"><b>You are done.</b>
      ${k}Put your phone face down and wait for dawn.</div></div></div>`;
  }
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
  return `<div class="night"><div class="inner">${rejoinBanner()}${forcedActions()}<h3>${esc(S.game.label)}</h3><h2>${esc(t.title)}</h2>${body}</div></div>`;
}

// ---------- chat ----------
// ui.thread: "" for everyone, or the other player's id. ui.read: thread -> last message id read.
function threadOf(m) { return m.to ? (m.from === S.me.id ? m.to : m.from || "anon") : ""; }
const sender = m => m.from === S.me.id ? (m.anon ? "You (anonymous)" : "You") : m.from ? nameOf(m.from) : "Anonymous";
function unread() {
  const read = ui.read || {}, out = { total: 0 };
  for (const m of S.chat || []) {
    if (m.from === S.me.id) continue;
    const t = threadOf(m);
    if (m.id > (read[t] || 0)) { out[t] = (out[t] || 0) + 1; out.total++; }
  }
  return out;
}
function chatView() {
  const t = ui.thread || "", msgs = (S.chat || []).filter(m => threadOf(m) === t);
  ui.read = { ...(ui.read || {}), [t]: msgs.length ? msgs[msgs.length - 1].id : (ui.read || {})[t] || 0 };
  const u = unread(), people = S.players.filter(p => p.id !== S.me.id);
  const anonIn = (S.chat || []).some(m => m.to && !m.from);
  const chip = (id, label) => `<button class="${t === id ? "sel" : ""}" data-act="thread" data-v="${id}">${esc(label)}${
    u[id] ? ` <span class="count">${u[id]}</span>` : ""}</button>`;
  const night = S.game.phase === "night";
  return `<div class="card stack"><h3>Chat</h3>
    <div class="threads">${chip("", "Everyone")}${anonIn ? chip("anon", "Anonymous") : ""}${people.map(p => chip(p.id, p.name + (p.agent ? " (agent)" : ""))).join("")}</div>
    <p class="small muted">${t === "anon" ? "Private messages sent to you without a name. You cannot reply."
      : t ? `Private with ${esc(nameOf(t))}. Nobody else sees these messages.` : "Everyone in the game sees these messages."}</p>
    <div class="msgs" id="msgs">${msgs.length ? msgs.map(m => `<div class="msg${m.from === S.me.id ? " mine" : ""}">
      <span class="lbl">${esc(sender(m))} · ${esc(m.label)}</span>${esc(m.text)}</div>`).join("")
      : `<p class="muted small">No messages yet.</p>`}</div>
    ${night ? `<p class="muted">Chat is closed at night. Talk again at dawn.</p>` : t === "anon" ? ""
      : `<div class="row"><input id="chat-text" class="grow" maxlength="300" placeholder="${t ? "Private message" : "Message everyone"}"
          value="${esc(ui.form["chat-text"] || "")}"><button class="primary" data-act="sendchat">Send</button></div>
        ${S.game.anon_chat ? `<label class="row small"><input type="checkbox" id="chat-anon" ${ui.anon ? "checked" : ""}
          style="width:auto"> Send without my name</label>` : ""}`}</div>`
    + feelCard();
}

// ---------- dawn: the narrator tells the story of the night ----------
function dawnView() {
  const n = S.narration, mine = n.narrator === S.me.id;
  let body;
  if (mine) {
    body = `<h2>You are the narrator</h2>
      <p>Read this story aloud to the town, or tell your own version. Only the deaths are true.
        The rest is made up, and its names are picked at random.</p>
      <div class="lines story">${n.story.map(l => `<p>${esc(l)}</p>`).join("")}</div>
      ${n.facts.length ? `<h3>Then announce</h3><div class="lines">${n.facts.map(l => `<p><b>${esc(l)}</b></p>`).join("")}</div>` : ""}
      <div class="stack"><button data-act="newstory">Give me another story</button>
        <button class="primary big" data-act="narrationdone">Morning announcement done</button></div>`;
  } else {
    body = `<div class="done"><b>${esc(nameOf(n.narrator))} is the narrator</b>
      Put your phone down and listen to the story of the night.</div>
      ${S.me.is_host ? `<p class="small muted" style="text-align:center">If ${esc(nameOf(n.narrator))} cannot read it,
        <button data-act="narrationdone">start the day without the story</button></p>` : ""}`;
  }
  return `<div class="night dawn"><div class="inner">${rejoinBanner()}${forcedActions()}<h3>Dawn, day ${S.game.day}</h3>${body}</div></div>`;
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
        const back = act === "join" && tokens.all().length;   // this browser may hold a seat in that game
        if (!name && !back) { toast("Enter your name first."); document.getElementById("name")?.focus(); return; }
        let r;
        if (act === "host") r = await api("/api/games", { name });
        else {
          const code = act === "join" ? d.code : document.getElementById("code").value.trim().toUpperCase();
          if (!code) return toast("Enter the game code.");
          r = await api(`/api/games/${code}/join`, { name, tokens: tokens.all() });
        }
        if (r.pending) { waitForRejoin(r.code, r.pending); return; }
        if (r.rejoined) toast("Welcome back.", "info");
        session.set({ code: r.code, token: r.token });
        connect(); return;
      }
      case "delgame": {
        if (!await ask(`Delete ${d.host}'s game ${d.code}? Everyone in its lobby goes back to the start page.`)) return;
        await api(`/api/games/${d.code}/delete`, {}); toast("Game deleted.", "info"); loadGames(); return;
      }
      case "archive": openArchive(); return;
      case "arcade": Arcade.open(); return;
      case "home": Arcade.stop(); ui.view = null; render(); return;
      case "archivetab": ui.archiveTab = d.v; render(); return;
      case "exportfile": {
        const sub = ui.archiveTab || "completed";
        await download(await fetch(`/api/archive/${sub}/${encodeURIComponent(d.file)}`)); return;
      }
      case "resumegame": {
        if (!await ask(`Resume ${d.host}'s game? It goes back into play, and the players can rejoin.`)) return;
        const r = await api(`/api/archive/paused/${encodeURIComponent(d.file)}/resume`, { name: ui.name || "", tokens: tokens.all() });
        ui.view = null; session.set({ code: r.code, token: r.token }); toast("The game is back. Its timer waits for you.", "info");
        connect(); return;
      }
      case "exportgame": {
        const s = session.get();
        await download(await fetch(`/api/games/${s.code}/export`, { method: "POST", headers: { "Content-Type": "application/json" },
                                                                    body: JSON.stringify({ token: s.token }) })); return;
      }
      case "narrationdone": send({ type: "narration_done" }); return;
      case "addagent": send({ type: "add_agent" }); return;
      case "fillagents": send({ type: "fill_agents" }); return;
      case "thread": ui.thread = d.v; render(); return;
      case "keyword": {
        const k = S.me.irl, word = document.getElementById("kw-w")?.value.trim();
        if (!word) return toast("Type the keyword first.");
        send({ type: "keyword", player: d.extra ? document.getElementById("kw-p").value : k.target, word }); return;
      }
      case "sendchat": {
        const el = document.getElementById("chat-text"), text = el?.value.trim();
        if (!text) return;
        send({ type: "chat", text, to: ui.thread || null, anon: !!(S.game.anon_chat && ui.anon) });
        ui.form["chat-text"] = ""; el.value = ""; return;
      }
      case "newstory": send({ type: "new_story" }); return;
      case "annoy": send({ type: "annoy" }); return;
      case "helper": send({ type: "setting", key: "helper", value: +d.v }); return;
      case "learner": send({ type: "learner", player: d.pid, on: d.v === "1" }); return;
      case "tip": {
        const q = document.getElementById("tip-q")?.value || "";
        ui.tipBusy = true; render(); send({ type: "tip", question: q }); return;
      }
      case "feel": feel.set(d.k, d.v === "1"); if (d.v === "1" && d.k === "sound") { unlockAudio(); setTimeout(() => cue("day"), 50); } render(); return;
      case "pausegame":
        if (await ask("Pause the game? Everyone goes back to the start page. Resume it from Archive, Paused.")) send({ type: "pause_game" });
        return;
      case "leave":
        if (!confirm(S?.game.phase === "lobby" ? "Leave this game? Your seat is freed."
                     : "Leave this game on this device? You can come back by joining with the same name.")) return;
        if (S?.game.phase === "lobby") send({ type: "leave" });
        setTimeout(() => { session.clear(); S = null; ws?.close(); render(); }, 150); return;
      case "toggle": send({ type: "setting", key: d.k, value: +d.v }); return;
      case "rejoin": send({ type: "rejoin_answer", request: d.id, allow: d.v === "1" }); return;
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
        if (d.k === "theme") { send({ type: "theme", theme: d.v }); return; }
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
      case "artistcheck": {
        const text = document.getElementById("da-artist-text")?.value.trim();
        if (!text) return toast("Type your question first.");
        ui.form["da-artist-text"] = text; ui.artistBusy = true; ui.artistPreview = null;
        send({ type: "artist_preview", text }); render(); return;
      }
      case "artistask": send({ type: "artist_confirm", preview: d.id }); ui.artistPreview = null; ui.form["da-artist-text"] = ""; return;
      case "artistclear": ui.artistPreview = null; render(); return;
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
app.addEventListener("input", ev => {
  if (ev.target.id === "name") ui.name = ev.target.value;
  if (ev.target.id === "chat-text") ui.form["chat-text"] = ev.target.value;
  if (ev.target.id === "chat-anon") ui.anon = ev.target.checked;
});
app.addEventListener("change", async ev => {
  const el = ev.target, d = el.dataset;
  if (el.id === "importfile" && el.files[0]) {
    try {
      const r = await api("/api/archive/import", { text: await el.files[0].text() });
      toast(`Imported to ${r.folder === "paused" ? "Paused" : "Completed"}.`, "info");
      ui.archiveTab = r.folder; openArchive();
    } catch (e) { toast(e.message); el.value = ""; }
    return;
  }
  if (el.id && (el.id.startsWith("da-") || el.id.startsWith("nt-"))) {
    ui.form[el.id] = el.value;
    if (el.tagName === "SELECT") render();  // a dropdown can change the form; text boxes must not redraw mid-click
  }
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
  if (ev.key === "Enter" && ev.target.id === "chat-text") { ev.preventDefault(); document.querySelector('[data-act="sendchat"]')?.click(); }
});

connect();
render();
