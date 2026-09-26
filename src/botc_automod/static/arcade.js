"use strict";
// Karma arcade: small games on the start page. A finished round goes to
// /api/arcade/score; the server keeps the boards and gives the karma
// (see arcade.py). The pool table is shared: the server runs its physics.
// Uses ui, esc, api, toast and app from app.js.

const Arcade = (() => {
  const A = { screen: "menu", info: null, game: null, stopFn: null, pool: null };
  const GAMES = [
    { id: "flappy", name: "Flappy Bat", how: "Tap to flap. Fly through the gaps in the towers." },
    { id: "dino", name: "Night Runner", how: "Tap to jump over the graves. It gets faster." },
    { id: "odd", name: "2047", how: "Swipe to slide. Two equal tiles join: 1+1 → 3, 3+3 → 7, and so on. Reach 2047." },
    { id: "blocks", name: "Blocks", how: "Tap the buttons, or use the arrow keys. Fill a row to clear it." },
    { id: "snake", name: "Snake", how: "Swipe to turn. Eat the lights, miss your tail." },
    { id: "pool", name: "Town Pool", how: "One table for everyone. Pocket balls for points." },
  ];
  const C = { bg: "#14111a", panel: "#1f1a28", panel2: "#2a2336", line: "#3a3148", text: "#ece6f5",
              muted: "#a89fb8", gold: "#d9b45b", evil: "#d8484a", good: "#4d8fe8", ok: "#4fb286" };
  const who = () => (ui.name || "").trim();

  // ---------- screens ----------
  async function open() {
    ui.view = "arcade"; A.screen = "menu"; render(); refresh();
  }
  async function refresh() {
    try { A.info = await api(`/api/arcade?name=${encodeURIComponent(who())}`); } catch (e) { toast(e.message); }
    if (A.screen === "menu" && ui.view === "arcade") render();
  }
  function karmaLine() {
    const i = A.info;
    if (!i) return "";
    if (!who()) return `<p class="small muted">Enter your name to earn karma.</p>`;
    return `<p class="small">Your karma: <b>${i.total ?? 0}</b> · from the arcade today: <b>${i.today}</b> of ${i.cap}</p>`;
  }
  function menu() {
    const i = A.info;
    const best = id => {
      if (id === "pool") return i?.pool_points ? `Your balls: ${i.pool_points}` : "";
      const b = i?.games[id]?.board || [];
      return b.length ? `Record: ${b[0].score} (${esc(b[0].name)})` : "No record yet";
    };
    return `<div class="archive-top"><button data-act="home">← Back</button><h1>Karma arcade</h1></div>
      <div class="card stack">
        <label for="arc-name" class="small muted">Your name (the same as in games)</label>
        <input id="arc-name" maxlength="24" autocomplete="nickname" value="${esc(ui.name || "")}" placeholder="Name">
        ${karmaLine()}
        <p class="small muted">Karma: +1 for your first real game each day, +1 for a new record,
          +1 for each ${i?.pool_per_karma ?? 3} balls you pocket at the pool table. At most ${i?.cap ?? 3} a day from the arcade.</p>
      </div>
      <div class="arc-grid">${GAMES.map(g => `<button class="arc-card" data-arc="play" data-g="${g.id}">
        <b>${g.name}</b><span class="small muted">${g.how}</span><span class="small arc-best">${best(g.id)}</span></button>`).join("")}</div>`;
  }
  function board(id) {
    const b = id === "pool" ? A.pool?.board || [] : A.info?.games[id]?.board || [];
    if (!b.length) return `<p class="small muted">No scores yet.</p>`;
    return `<ol class="arc-board">${b.map(e => `<li class="${e.name.toLowerCase() === who().toLowerCase() ? "me" : ""}">
      <span>${esc(e.name)}</span><b>${e.score}</b></li>`).join("")}</ol>`;
  }
  function gameScreen() {
    const g = GAMES.find(x => x.id === A.game);
    return `<div class="archive-top"><button data-arc="menu">← Arcade</button><h1>${g.name}</h1>
      <div class="arc-score" id="arc-score"></div></div>
      <p class="small muted">${g.how}</p>
      <div id="arc-stage" class="arc-stage"></div>
      <div id="arc-under"></div>
      <div class="card stack"><h3>${A.game === "pool" ? "Balls pocketed" : "Best scores"}</h3><div id="arc-board">${board(A.game)}</div></div>`;
  }
  function render() {
    if (A.screen === "game" && document.getElementById("arc-stage")) return;   // do not wipe a running game
    app.innerHTML = A.screen === "game" ? gameScreen() : menu();
    if (A.screen === "game") start(A.game);
  }
  function stop() {
    A.stopFn?.(); A.stopFn = null;
  }
  function play(id) {
    if (!who()) { toast("Enter your name first."); document.getElementById("arc-name")?.focus(); return; }
    stop(); A.game = id; A.screen = "game"; app.innerHTML = ""; render(); window.scrollTo(0, 0);
  }
  function toMenu() { stop(); A.screen = "menu"; render(); refresh(); }
  const setScore = s => { const el = document.getElementById("arc-score"); if (el) el.textContent = s; };

  async function finished(id, score, secs) {
    const under = document.getElementById("arc-under");
    if (under) under.innerHTML = `<div class="card stack arc-over"><h2>Score: ${score}</h2><p class="small muted">Sending...</p></div>`;
    let msg = "";
    try {
      const r = await api("/api/arcade/score", { name: who(), game: id, score, secs });
      A.info && (A.info.games[id].board = r.board, A.info.total = r.total, A.info.today = r.today);
      const bits = [];
      if (r.record) bits.push("A new record!");
      if (r.karma) bits.push(`Karma +${r.karma} (${r.why.join(", ")}). You have ${r.total}.`);
      else if (r.today >= r.cap) bits.push(`No more arcade karma today (${r.cap} of ${r.cap}).`);
      else if (score < r.real_try && !r.played) bits.push(`Score ${r.real_try} or more for today's first-game karma.`);
      msg = bits.join(" ");
      const bd = document.getElementById("arc-board");
      if (bd) bd.innerHTML = board(id);
    } catch (e) { msg = e.message; }
    const el = document.getElementById("arc-under");
    if (el) el.innerHTML = `<div class="card stack arc-over"><h2>Score: ${score}</h2>${msg ? `<p>${esc(msg)}</p>` : ""}
      <div class="row"><button class="primary grow" data-arc="again">Play again</button><button class="grow" data-arc="menu">Arcade</button></div></div>`;
  }

  // ---------- shared game parts ----------
  // A canvas with a fixed logical size (lw x lh), scaled to fit the page.
  function stage(lw, lh, maxFrac = 0.62) {
    const host = document.getElementById("arc-stage");
    const cv = document.createElement("canvas");
    const avail = Math.min(host.clientWidth || 340, 480);
    let w = avail, h = w * lh / lw;
    const maxH = Math.max(260, window.innerHeight * maxFrac);
    if (h > maxH) { h = maxH; w = h * lw / lh; }
    const dpr = window.devicePixelRatio || 1;
    cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr);
    cv.style.width = w + "px"; cv.style.height = h + "px";
    host.appendChild(cv);
    const ctx = cv.getContext("2d");
    const k = w / lw;
    ctx.setTransform(dpr * k, 0, 0, dpr * k, 0, 0);
    // pointer position in logical units
    const at = ev => { const r = cv.getBoundingClientRect(); return [(ev.clientX - r.left) / k, (ev.clientY - r.top) / k]; };
    return { cv, ctx, lw, lh, at };
  }
  function loop(step) {
    let last = performance.now(), id = 0, on = true;
    const f = now => {
      if (!on) return;
      step(Math.min(0.05, (now - last) / 1000)); last = now;
      id = requestAnimationFrame(f);
    };
    id = requestAnimationFrame(f);
    return () => { on = false; cancelAnimationFrame(id); };
  }
  // Taps and swipes on an element, and arrow keys / space.
  function gestures(el, cb) {
    let sx = 0, sy = 0, down = false;
    el.addEventListener("pointerdown", ev => { down = true; sx = ev.clientX; sy = ev.clientY; ev.preventDefault(); });
    el.addEventListener("pointerup", ev => {
      if (!down) return; down = false;
      const dx = ev.clientX - sx, dy = ev.clientY - sy;
      if (Math.hypot(dx, dy) < 24) cb("tap", ev);
      else cb(Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? "right" : "left") : (dy > 0 ? "down" : "up"), ev);
    });
    const keys = { ArrowLeft: "left", ArrowRight: "right", ArrowUp: "up", ArrowDown: "down", " ": "tap", w: "up", a: "left", s: "down", d: "right" };
    const kd = ev => {
      if (!keys[ev.key] || ["INPUT", "TEXTAREA"].includes(document.activeElement?.tagName)) return;
      ev.preventDefault(); cb(keys[ev.key], ev);
    };
    document.addEventListener("keydown", kd);
    return () => document.removeEventListener("keydown", kd);
  }
  function text(ctx, s, x, y, size = 18, color = C.text, align = "center") {
    ctx.fillStyle = color; ctx.font = `700 ${size}px system-ui, sans-serif`; ctx.textAlign = align; ctx.textBaseline = "middle";
    ctx.fillText(s, x, y);
  }
  const rnd = (a, b) => a + Math.random() * (b - a);

  function start(id) {
    const under = document.getElementById("arc-under");
    under.innerHTML = "";
    setScore("");
    A.stopFn = ({ flappy, dino, odd, blocks, snake, pool }[id])();
  }

  // ---------- Flappy Bat ----------
  function flappy() {
    const S = stage(320, 480), { ctx } = S;
    const GAP = 135, SPEED = 140, EVERY = 1.55;
    let bat, pipes, score, t, since, state, t0;
    const reset = () => { bat = { y: 220, vy: 0 }; pipes = []; score = 0; t = 0; since = EVERY; state = "ready"; setScore(0); };
    reset();
    const flap = () => {
      if (state === "over") return;
      if (state === "ready") { state = "run"; t0 = performance.now(); }
      bat.vy = -400;
    };
    // Flap when the finger goes down (not on release); keys come through gestures().
    const unkey = gestures(S.cv, (d, ev) => ev.type === "keydown" && (d === "tap" || d === "up") && flap());
    S.cv.addEventListener("pointerdown", flap);
    const over = () => { state = "over"; finished("flappy", score, (performance.now() - t0) / 1000); };
    const stopLoop = loop(dt => {
      t += dt;
      if (state === "run") {
        bat.vy += 1300 * dt; bat.y += bat.vy * dt;
        since += dt;
        if (since >= EVERY) { since = 0; pipes.push({ x: 340, gy: rnd(70, 480 - 70 - GAP), done: false }); }
        for (const p of pipes) {
          p.x -= SPEED * dt;
          if (!p.done && p.x + 26 < 80) { p.done = true; score++; setScore(score); }
          if (p.x < 80 + 13 && p.x + 52 > 80 - 13 && (bat.y - 11 < p.gy || bat.y + 11 > p.gy + GAP)) over();
        }
        pipes = pipes.filter(p => p.x > -60);
        if (bat.y > 470 || bat.y < -40) over();
      } else if (state === "ready") bat.y = 220 + Math.sin(t * 3) * 8;
      // draw
      const g = ctx.createLinearGradient(0, 0, 0, 480);
      g.addColorStop(0, "#0d0b14"); g.addColorStop(1, "#2a2140");
      ctx.fillStyle = g; ctx.fillRect(0, 0, 320, 480);
      ctx.fillStyle = "#f4ecc8"; ctx.beginPath(); ctx.arc(250, 70, 26, 0, 7); ctx.fill();
      ctx.fillStyle = C.bg; ctx.beginPath(); ctx.arc(240, 62, 24, 0, 7); ctx.fill();
      for (const p of pipes) {
        ctx.fillStyle = "#4a4060";
        ctx.fillRect(p.x, 0, 52, p.gy); ctx.fillRect(p.x, p.gy + GAP, 52, 480 - p.gy - GAP);
        ctx.fillStyle = C.gold;
        ctx.fillRect(p.x - 3, p.gy - 12, 58, 12); ctx.fillRect(p.x - 3, p.gy + GAP, 58, 12);
      }
      // the bat
      const wing = Math.sin(t * 22) * 7;
      ctx.save(); ctx.translate(80, bat.y); ctx.rotate(Math.max(-0.5, Math.min(0.8, bat.vy / 700)));
      ctx.fillStyle = "#1b1624"; ctx.strokeStyle = C.muted; ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.moveTo(-4, 0); ctx.lineTo(-24, -8 - wing); ctx.lineTo(-16, 4); ctx.lineTo(-6, 4); ctx.closePath(); ctx.fill(); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(4, 0); ctx.lineTo(24, -8 - wing); ctx.lineTo(16, 4); ctx.lineTo(6, 4); ctx.closePath(); ctx.fill(); ctx.stroke();
      ctx.beginPath(); ctx.arc(0, 0, 9, 0, 7); ctx.fill(); ctx.stroke();
      ctx.fillStyle = C.evil; ctx.fillRect(2, -3, 3, 3);
      ctx.restore();
      text(ctx, String(score), 160, 40, 32);
      if (state === "ready") text(ctx, "Tap to start", 160, 300, 20, C.gold);
    });
    return () => { stopLoop(); unkey(); };
  }

  // ---------- Night Runner (the dinosaur game) ----------
  function dino() {
    const S = stage(480, 200), { ctx } = S;
    const GROUND = 170;
    let me, obs, speed, t, next, state, t0, score;
    const reset = () => { me = { y: GROUND, vy: 0 }; obs = []; speed = 250; t = 0; next = 1; state = "ready"; score = 0; setScore(0); };
    reset();
    const jump = () => {
      if (state === "over") return;
      if (state === "ready") { state = "run"; t0 = performance.now(); }
      if (me.y >= GROUND) me.vy = -640;
    };
    const unkey = gestures(S.cv, (d, ev) => ev.type === "keydown" && (d === "tap" || d === "up") && jump());
    S.cv.addEventListener("pointerdown", jump);
    const over = () => { state = "over"; finished("dino", score, (performance.now() - t0) / 1000); };
    const stopLoop = loop(dt => {
      if (state === "run") {
        t += dt; speed += 9 * dt;
        score = Math.floor(t * 10); setScore(score);
        me.vy += 2100 * dt; me.y = Math.min(GROUND, me.y + me.vy * dt);
        next -= dt;
        if (next <= 0) {
          const bat = t > 20 && Math.random() < 0.25;
          obs.push(bat ? { x: 500, w: 26, h: 14, y: GROUND - 58 - rnd(0, 10), bat: true }
                       : { x: 500, w: rnd(14, 26), h: rnd(24, 44), y: GROUND });
          next = rnd(0.75, 1.6) * 260 / speed + 0.35;
        }
        for (const o of obs) {
          o.x -= speed * dt;
          if (o.x < 60 + 12 && o.x + o.w > 60 - 12 && me.y > o.y - o.h + 4 && me.y - 34 < o.y - 2) over();
        }
        obs = obs.filter(o => o.x > -40);
      }
      ctx.fillStyle = "#15121c"; ctx.fillRect(0, 0, 480, 200);
      ctx.fillStyle = "#7e7396";
      for (let i = 0; i < 18; i++) ctx.fillRect((i * 97 - t * 20) % 480 + (i * 97 - t * 20 < 0 ? 480 : 0), 20 + (i * 37) % 90, 2, 2);
      ctx.strokeStyle = C.line; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(0, GROUND + 1); ctx.lineTo(480, GROUND + 1); ctx.stroke();
      // runner: a hooded figure
      ctx.fillStyle = C.gold;
      ctx.beginPath(); ctx.moveTo(48, me.y); ctx.lineTo(60, me.y - 34); ctx.lineTo(72, me.y); ctx.closePath(); ctx.fill();
      ctx.beginPath(); ctx.arc(60, me.y - 34, 7, 0, 7); ctx.fill();
      for (const o of obs) {
        if (o.bat) {
          ctx.fillStyle = C.muted; ctx.beginPath();
          ctx.moveTo(o.x, o.y - 7); ctx.lineTo(o.x + 13, o.y - 3 - (Math.sin(t * 20) * 6)); ctx.lineTo(o.x + 26, o.y - 7); ctx.lineTo(o.x + 13, o.y); ctx.fill();
        } else {
          ctx.fillStyle = "#5c536f";
          ctx.beginPath(); ctx.moveTo(o.x, o.y); ctx.lineTo(o.x, o.y - o.h + o.w / 2);
          ctx.arc(o.x + o.w / 2, o.y - o.h + o.w / 2, o.w / 2, Math.PI, 0); ctx.lineTo(o.x + o.w, o.y); ctx.fill();
        }
      }
      text(ctx, String(score), 460, 20, 16, C.text, "right");
      if (state === "ready") text(ctx, "Tap to start", 240, 90, 18, C.gold);
    });
    return () => { stopLoop(); unkey(); };
  }

  // ---------- 2047: 2048 with odd numbers ----------
  // Tiles are 1, 3, 7, 15, ... (2^n - 1). Two equal tiles join into 2a + 1.
  function odd() {
    const S = stage(320, 320), { ctx } = S;
    let grid = Array.from({ length: 4 }, () => Array(4).fill(0)), score = 0, over = false, t0 = null, anim = 0;
    const spawn = () => {
      const free = [];
      grid.forEach((r, y) => r.forEach((v, x) => !v && free.push([x, y])));
      if (!free.length) return;
      const [x, y] = free[Math.floor(Math.random() * free.length)];
      grid[y][x] = Math.random() < 0.9 ? 1 : 3;
    };
    spawn(); spawn(); setScore(0);
    const slideRow = row => {
      const v = row.filter(Boolean), out = [];
      for (let i = 0; i < v.length; i++) {
        if (v[i] === v[i + 1]) { out.push(v[i] * 2 + 1); score += v[i] * 2 + 1; i++; }
        else out.push(v[i]);
      }
      while (out.length < 4) out.push(0);
      return out;
    };
    const move = dir => {
      if (over) return;
      const before = JSON.stringify(grid);
      const get = (i, j) => dir === "left" ? grid[i][j] : dir === "right" ? grid[i][3 - j] : dir === "up" ? grid[j][i] : grid[3 - j][i];
      const set = (i, j, v) => { if (dir === "left") grid[i][j] = v; else if (dir === "right") grid[i][3 - j] = v; else if (dir === "up") grid[j][i] = v; else grid[3 - j][i] = v; };
      for (let i = 0; i < 4; i++) {
        const row = slideRow([0, 1, 2, 3].map(j => get(i, j)));
        row.forEach((v, j) => set(i, j, v));
      }
      if (JSON.stringify(grid) === before) return;
      t0 ??= performance.now();
      spawn(); setScore(score); anim = 1;
      const canMove = grid.some((r, y) => r.some((v, x) => !v || (x < 3 && r[x + 1] === v) || (y < 3 && grid[y + 1][x] === v)));
      if (!canMove) { over = true; finished("odd", score, (performance.now() - t0) / 1000); }
    };
    const unkey = gestures(S.cv, d => d !== "tap" && move(d));
    const colors = { 1: "#3b3350", 3: "#4b3f69", 7: "#5b4a86", 15: "#3f6fb0", 31: "#3b8f8a", 63: "#4fb286", 127: "#a8a04a",
                     255: "#d9b45b", 511: "#d9894a", 1023: "#d8484a", 2047: "#f4ecc8" };
    const stopLoop = loop(dt => {
      anim = Math.max(0, anim - dt * 6);
      ctx.fillStyle = C.panel; ctx.fillRect(0, 0, 320, 320);
      for (let y = 0; y < 4; y++) for (let x = 0; x < 4; x++) {
        const v = grid[y][x];
        ctx.fillStyle = v ? colors[v] || "#fff" : C.panel2;
        ctx.beginPath(); ctx.roundRect(8 + x * 78, 8 + y * 78, 70, 70, 10); ctx.fill();
        if (v) text(ctx, String(v), 43 + x * 78, 43 + y * 78, v > 999 ? 20 : v > 99 ? 24 : 28, v >= 255 ? "#1a1408" : C.text);
      }
      if (over) { ctx.fillStyle = "rgba(20,17,26,.7)"; ctx.fillRect(0, 0, 320, 320); text(ctx, "No moves left", 160, 160, 24, C.gold); }
    });
    return () => { stopLoop(); unkey(); };
  }

  // ---------- Blocks (a small Tetris) ----------
  function blocks() {
    const COLS = 10, ROWS = 20, B = 16;
    const S = stage(COLS * B, ROWS * B, 0.55), { ctx } = S;
    const SHAPES = [
      [[1, 1, 1, 1]], [[1, 1], [1, 1]], [[0, 1, 0], [1, 1, 1]], [[1, 0, 0], [1, 1, 1]],
      [[0, 0, 1], [1, 1, 1]], [[1, 1, 0], [0, 1, 1]], [[0, 1, 1], [1, 1, 0]],
    ];
    const COL = ["#4d8fe8", "#d9b45b", "#9a6ad8", "#4fb286", "#d9894a", "#d8484a", "#3fb0c0"];
    const well = Array.from({ length: ROWS }, () => Array(COLS).fill(0));
    let piece, score = 0, lines = 0, over = false, fall = 0, t0 = performance.now();
    const fits = (m, px, py) => m.every((r, y) => r.every((v, x) => !v || (px + x >= 0 && px + x < COLS && py + y < ROWS && (py + y < 0 || !well[py + y][px + x]))));
    const newPiece = () => {
      const k = Math.floor(Math.random() * SHAPES.length);
      piece = { m: SHAPES[k], c: k + 1, x: 3, y: -1 };
      if (!fits(piece.m, piece.x, piece.y)) { over = true; finished("blocks", score, (performance.now() - t0) / 1000); }
    };
    const lock = () => {
      piece.m.forEach((r, y) => r.forEach((v, x) => { if (v && piece.y + y >= 0) well[piece.y + y][piece.x + x] = piece.c; }));
      let n = 0;
      for (let y = ROWS - 1; y >= 0; y--) if (well[y].every(Boolean)) { well.splice(y, 1); well.unshift(Array(COLS).fill(0)); n++; y++; }
      if (n) { lines += n; score += [0, 100, 300, 500, 800][n]; setScore(score); }
      newPiece();
    };
    const act = a => {
      if (over) return;
      if (a === "left" && fits(piece.m, piece.x - 1, piece.y)) piece.x--;
      if (a === "right" && fits(piece.m, piece.x + 1, piece.y)) piece.x++;
      if (a === "rot" || a === "up") {
        const r = piece.m[0].map((_, i) => piece.m.map(row => row[i]).reverse());
        for (const kick of [0, -1, 1, -2, 2]) if (fits(r, piece.x + kick, piece.y)) { piece.m = r; piece.x += kick; break; }
      }
      if (a === "down") { while (fits(piece.m, piece.x, piece.y + 1)) { piece.y++; score += 1; } setScore(score); lock(); }
    };
    newPiece(); setScore(0);
    const unkey = gestures(S.cv, d => act(d === "tap" ? "rot" : d));
    const under = document.getElementById("arc-under");
    under.innerHTML = `<div class="arc-pad"><button data-b="left" aria-label="Left">◀</button><button data-b="rot" aria-label="Turn">⟳</button>
      <button data-b="down" aria-label="Drop">▼</button><button data-b="right" aria-label="Right">▶</button></div>`;
    under.querySelector(".arc-pad").addEventListener("pointerdown", ev => {
      const b = ev.target.closest("[data-b]"); if (b) { ev.preventDefault(); act(b.dataset.b); }
    });
    const stopLoop = loop(dt => {
      if (!over) {
        fall += dt;
        const every = Math.max(0.1, 0.7 - Math.floor(lines / 10) * 0.07);
        if (fall >= every) { fall = 0; if (fits(piece.m, piece.x, piece.y + 1)) piece.y++; else lock(); }
      }
      ctx.fillStyle = C.panel; ctx.fillRect(0, 0, COLS * B, ROWS * B);
      const cell = (x, y, c) => { ctx.fillStyle = COL[c - 1]; ctx.fillRect(x * B + 1, y * B + 1, B - 2, B - 2); };
      well.forEach((r, y) => r.forEach((v, x) => v && cell(x, y, v)));
      if (!over) piece.m.forEach((r, y) => r.forEach((v, x) => v && piece.y + y >= 0 && cell(piece.x + x, piece.y + y, piece.c)));
      if (over) text(ctx, "Game over", COLS * B / 2, ROWS * B / 2, 20, C.gold);
    });
    return () => { stopLoop(); unkey(); };
  }

  // ---------- Snake ----------
  function snake() {
    const N = 16, B = 20;
    const S = stage(N * B, N * B), { ctx } = S;
    let body = [[8, 8], [7, 8], [6, 8]], dir = [1, 0], want = [1, 0], food, score = 0, over = false, acc = 0, started = false, t0;
    const place = () => { do food = [Math.floor(Math.random() * N), Math.floor(Math.random() * N)]; while (body.some(b => b[0] === food[0] && b[1] === food[1])); };
    place(); setScore(0);
    const D = { left: [-1, 0], right: [1, 0], up: [0, -1], down: [0, 1] };
    const unkey = gestures(S.cv, d => {
      if (over || !D[d]) return;
      if (!started) { started = true; t0 = performance.now(); }
      if (D[d][0] !== -dir[0] || D[d][1] !== -dir[1]) want = D[d];
    });
    const stopLoop = loop(dt => {
      if (started && !over) {
        acc += dt;
        const every = Math.max(0.07, 0.16 - score * 0.003);
        if (acc >= every) {
          acc = 0; dir = want;
          const h = [body[0][0] + dir[0], body[0][1] + dir[1]];
          if (h[0] < 0 || h[1] < 0 || h[0] >= N || h[1] >= N || body.some(b => b[0] === h[0] && b[1] === h[1])) {
            over = true; finished("snake", score, (performance.now() - t0) / 1000);
          } else {
            body.unshift(h);
            if (h[0] === food[0] && h[1] === food[1]) { score++; setScore(score); place(); } else body.pop();
          }
        }
      }
      ctx.fillStyle = C.panel; ctx.fillRect(0, 0, N * B, N * B);
      ctx.fillStyle = C.gold; ctx.beginPath(); ctx.arc(food[0] * B + B / 2, food[1] * B + B / 2, B / 3, 0, 7); ctx.fill();
      body.forEach((b, i) => { ctx.fillStyle = i ? C.ok : "#8fe0b8"; ctx.fillRect(b[0] * B + 1, b[1] * B + 1, B - 2, B - 2); });
      if (!started) text(ctx, "Swipe to start", N * B / 2, N * B / 2 + 50, 18, C.gold);
      if (over) text(ctx, "Game over", N * B / 2, N * B / 2, 22, C.gold);
    });
    return () => { stopLoop(); unkey(); };
  }

  // ---------- Town Pool ----------
  // Put a thumb anywhere, pull back (the pull sets the power), then slide
  // forward along the same line and past the start point. Drift off the
  // line while sliding forward bends the shot. Only the cue ball is hit.
  function pool() {
    const TW = 100, TH = 50, R = 1.25, RAIL = 4;
    const host = document.getElementById("arc-stage");
    const portrait = (host.clientWidth || 340) < 560;
    // logical canvas: the table plus a rail; portrait turns the table on its side
    const LW = portrait ? TH + 2 * RAIL : TW + 2 * RAIL, LH = portrait ? TW + 2 * RAIL : TH + 2 * RAIL;
    const S = stage(LW, LH, 0.66), { ctx } = S;
    const toScr = (x, y) => portrait ? [RAIL + (TH - y), RAIL + x] : [RAIL + x, RAIL + y];
    const toTab = (sx, sy) => portrait ? [sy - RAIL, TH - (sx - RAIL)] : [sx - RAIL, sy - RAIL];
    const COLORS = [null, "#e8c33a", "#2f5fd0", "#d8484a", "#7a3fb0", "#e0782a", "#2f9a55", "#8a2b2b", "#111",
                    "#e8c33a", "#2f5fd0", "#d8484a", "#7a3fb0", "#e0782a", "#2f9a55", "#8a2b2b"];
    const POCKETS = [[0, 0], [TW / 2, -0.6], [TW, 0], [0, TH], [TW / 2, TH + 0.6], [TW, TH]];
    const MAXPULL = 22;
    let table = null, shown = null, playing = null, busy = false, poll = 0, aim = null, on = true;
    const under = document.getElementById("arc-under");
    const status = () => {
      if (!table) return "Loading the table...";
      if (playing) return "The balls are rolling...";
      const me = who().toLowerCase(), wait = Math.ceil(table.wait);
      const last = table.last_note ? `${esc(table.last_note)}.` : "";
      if (table.last_by.toLowerCase() === me && wait > 0) return `${last} You shot last: wait ${wait} s, or let someone else shoot.`;
      return `${last} The table is yours: put your thumb down, pull back, then slide forward.`;
    };
    const drawStatus = () => { under.innerHTML = `<p class="small arc-pool-status">${status()}</p>`; };

    async function fetchTable() {
      try {
        const t = await api(`/api/arcade/pool?since=${table ? table.version : -1}`);
        const fresh = !table;
        if (!table || t.version !== table.version) {
          if (!fresh && t.frames?.length) play(t.frames, t);
          else { table = t; shown = t.balls; }
        } else { table.wait = t.wait; table.board = t.board; }
        A.pool = t; const bd = document.getElementById("arc-board"); if (bd && !playing) bd.innerHTML = board("pool");
      } catch {}
      if (!playing) drawStatus();
    }
    function play(frames, t) {
      playing = { frames, i: 0, acc: 0, then: t };
    }
    fetchTable();

    async function shoot(angle, power) {
      if (busy || !table) return;
      busy = true;
      try {
        const r = await api("/api/arcade/pool/shot", { name: who(), version: table.version, angle, power });
        play(r.pool.frames, r.pool);
        const bits = [];
        if (r.points > 0) bits.push(`+${r.points} ball${r.points > 1 ? "s" : ""}`);
        if (r.points < 0) bits.push("Cue ball sunk: −1");
        if (r.karma) bits.push(`karma +${r.karma} (you have ${r.total})`);
        if (bits.length) setTimeout(() => toast(bits.join(" · "), "info"), r.pool.frames.length * 33);
      } catch (e) { toast(e.message); table = null; fetchTable(); }
      busy = false;
    }

    // --- the stroke ---
    const cv = S.cv;
    cv.addEventListener("pointerdown", ev => {
      if (!table || playing || busy) return;
      ev.preventDefault(); cv.setPointerCapture(ev.pointerId);
      const [x, y] = toTab(...S.at(ev));
      aim = { a: [x, y], b: [x, y], pull: 0, stage: "pull", perp: [], id: ev.pointerId };
    });
    cv.addEventListener("pointermove", ev => {
      if (!aim || ev.pointerId !== aim.id) return;
      const [x, y] = toTab(...S.at(ev));
      aim.f = [x, y];
      const dx = x - aim.a[0], dy = y - aim.a[1], d = Math.hypot(dx, dy);
      if (aim.stage === "pull") {
        if (d >= aim.pull) { aim.pull = Math.min(d, MAXPULL * 1.2); aim.b = [x, y]; }
        else if (aim.pull > 2 && d < aim.pull - 1.2) aim.stage = "stroke";   // the thumb comes forward: lock the line
      }
      if (aim.stage === "stroke") {
        // line from b (back) through a (start); u is the shot direction
        const L = Math.hypot(aim.a[0] - aim.b[0], aim.a[1] - aim.b[1]);
        const ux = (aim.a[0] - aim.b[0]) / L, uy = (aim.a[1] - aim.b[1]) / L;
        const along = (x - aim.b[0]) * ux + (y - aim.b[1]) * uy;
        const perp = -(x - aim.b[0]) * uy + (y - aim.b[1]) * ux;   // + is to the left of the line
        aim.perp.push(perp);
        if (along >= L) {   // the thumb passed the start point: shoot
          const drift = aim.perp.reduce((s, v) => s + v, 0) / aim.perp.length;
          const worst = aim.perp.reduce((s, v) => Math.max(s, Math.abs(v)), 0);
          const err = Math.atan2(drift * 0.6 + Math.sign(drift) * worst * 0.2, L);
          const angle = Math.atan2(uy, ux) + err;
          const power = Math.min(1, aim.pull / MAXPULL);
          aim = null;
          shoot(angle, power);
        }
      }
    });
    const cancel = ev => {
      if (!aim || ev.pointerId !== aim.id) return;
      if (aim.pull > 2) toast("No shot. Slide forward past where you started.");
      aim = null;
    };
    cv.addEventListener("pointerup", cancel);
    cv.addEventListener("pointercancel", cancel);

    const circle = (x, y, r, fill) => { const [sx, sy] = toScr(x, y); ctx.fillStyle = fill; ctx.beginPath(); ctx.arc(sx, sy, r, 0, 7); ctx.fill(); };
    const line = (x1, y1, x2, y2, color, w, dash = []) => {
      const [a, b] = toScr(x1, y1), [c, d] = toScr(x2, y2);
      ctx.strokeStyle = color; ctx.lineWidth = w; ctx.setLineDash(dash); ctx.beginPath(); ctx.moveTo(a, b); ctx.lineTo(c, d); ctx.stroke(); ctx.setLineDash([]);
    };
    const stopLoop = loop(dt => {
      poll += dt;
      if (poll > 1.5 && !playing && !aim && on) { poll = 0; fetchTable(); }
      if (playing) {
        playing.acc += dt * 30;
        playing.i = Math.min(playing.frames.length - 1, Math.floor(playing.acc));
        shown = playing.frames[playing.i];
        if (playing.i >= playing.frames.length - 1) {
          table = playing.then; shown = table.balls; playing = null; drawStatus();
          A.pool = table; const bd = document.getElementById("arc-board"); if (bd) bd.innerHTML = board("pool");
        }
      }
      // table
      ctx.fillStyle = "#4a2e1c"; ctx.fillRect(0, 0, LW, LH);
      ctx.fillStyle = "#1d6b45"; ctx.fillRect(RAIL, RAIL, LW - 2 * RAIL, LH - 2 * RAIL);
      for (const [px, py] of POCKETS) circle(px, py, 2.4, "#0a0a0a");
      if (!shown) return;
      shown.forEach((b, i) => {
        if (!b) return;
        if (i === 0) return circle(b[0], b[1], R, "#f4f1e6");
        if (i > 8) { circle(b[0], b[1], R, "#f4f1e6"); circle(b[0], b[1], R * 0.62, COLORS[i]); }
        else circle(b[0], b[1], R, COLORS[i]);
      });
      // the cue and the aim line
      const cue = shown[0];
      if (aim && cue && aim.pull > 0.5) {
        const L = Math.hypot(aim.a[0] - aim.b[0], aim.a[1] - aim.b[1]) || 1;
        const ux = (aim.a[0] - aim.b[0]) / L, uy = (aim.a[1] - aim.b[1]) / L;
        const power = Math.min(1, aim.pull / MAXPULL);
        let back = 1.8 + power * 8;
        if (aim.stage === "stroke" && aim.f) {
          const along = (aim.f[0] - aim.b[0]) * ux + (aim.f[1] - aim.b[1]) * uy;
          back = 1.8 + Math.max(0, (L - along) / L) * power * 8;
        }
        line(cue[0], cue[1], cue[0] + ux * 30, cue[1] + uy * 30, "rgba(255,255,255,.35)", 0.3, [1, 1]);
        line(cue[0] - ux * back, cue[1] - uy * back, cue[0] - ux * (back + 28), cue[1] - uy * (back + 28), "#d9b98a", 0.9);
        // the stroke line under the thumb, and how far it drifts
        line(aim.b[0], aim.b[1], aim.a[0] + ux * 4, aim.a[1] + uy * 4, "rgba(217,180,91,.5)", 0.25, [0.8, 0.8]);
        if (aim.f) circle(aim.f[0], aim.f[1], 0.8, "rgba(217,180,91,.8)");
        const [sx, sy] = toScr(cue[0], cue[1]);
        ctx.fillStyle = C.gold; ctx.font = "700 3px system-ui"; ctx.textAlign = "center";
        ctx.fillText(`${Math.round(power * 100)}%`, sx, sy - 3);
      }
    });
    return () => { on = false; stopLoop(); };
  }

  // ---------- events ----------
  app.addEventListener("click", ev => {
    if (ui.view !== "arcade") return;
    const b = ev.target.closest("[data-arc]");
    if (!b) return;
    const d = b.dataset;
    if (d.arc === "play") play(d.g);
    else if (d.arc === "menu") toMenu();
    else if (d.arc === "again") { stop(); document.getElementById("arc-stage").innerHTML = ""; start(A.game); }
  });
  app.addEventListener("change", ev => {
    if (ev.target.id === "arc-name") { ui.name = ev.target.value.trim(); refresh(); }
  });
  app.addEventListener("input", ev => { if (ev.target.id === "arc-name") ui.name = ev.target.value; });

  return { open, render, stop };
})();
