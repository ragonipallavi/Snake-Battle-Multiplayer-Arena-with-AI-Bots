/* ── Snake Battle — Client ──────────────────────────────────────────────────── */

const socket = io();

// DOM
const lobbyScreen   = document.getElementById('lobby');
const gameScreen    = document.getElementById('game');
const gameoverScreen= document.getElementById('gameover');
const joinBtn       = document.getElementById('join-btn');
const nameInput     = document.getElementById('name-input');
const canvas        = document.getElementById('game-canvas');
const ctx           = canvas.getContext('2d');
const hudRoom       = document.getElementById('room-label');
const hudCountdown  = document.getElementById('countdown-display');
const scoreboard    = document.getElementById('scoreboard');
const deadBanner    = document.getElementById('dead-banner');
const goTitle       = document.getElementById('go-title');
const goWinner      = document.getElementById('go-winner');
const goScores      = document.getElementById('go-scores');
const restartBtn    = document.getElementById('restart-btn');

// State
let myId       = null;
let myColor    = '#00ff88';
let gridW      = 40;
let gridH      = 30;
let cellSize   = 16;
let lastState  = null;
let animFrame  = null;
let particles  = [];

// ── Screens ──────────────────────────────────────────────────────────────────
function showScreen(id) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  document.getElementById(id).style.display = 'flex';
  document.getElementById(id).classList.add('active');
}

// ── Canvas sizing ────────────────────────────────────────────────────────────
function resizeCanvas() {
  const wrap = document.getElementById('canvas-wrap');
  const dpad = document.getElementById('dpad');
  const hudH = document.getElementById('hud').offsetHeight;
  const dpadH = window.innerWidth < 900 ? dpad.offsetHeight + 28 : 0;
  const availH = window.innerHeight - hudH - dpadH - 16;
  const availW = wrap.offsetWidth - 8;
  cellSize = Math.max(8, Math.floor(Math.min(availW / gridW, availH / gridH)));
  canvas.width  = cellSize * gridW;
  canvas.height = cellSize * gridH;
  if (lastState) drawState(lastState);
}
window.addEventListener('resize', resizeCanvas);

// ── Join ─────────────────────────────────────────────────────────────────────
joinBtn.addEventListener('click', doJoin);
nameInput.addEventListener('keydown', e => { if (e.key === 'Enter') doJoin(); });

function doJoin() {
  const name = nameInput.value.trim() || 'Snake';
  socket.emit('join', { name });
  showScreen('game');
  setTimeout(resizeCanvas, 50);
}

// ── Controls ─────────────────────────────────────────────────────────────────
const KEY_MAP = {
  ArrowUp:    [0, -1], w: [0, -1], W: [0, -1],
  ArrowDown:  [0,  1], s: [0,  1], S: [0,  1],
  ArrowLeft:  [-1, 0], a: [-1, 0], A: [-1, 0],
  ArrowRight: [ 1, 0], d: [ 1, 0], D: [ 1, 0],
};

document.addEventListener('keydown', e => {
  const dir = KEY_MAP[e.key];
  if (dir) {
    e.preventDefault();
    socket.emit('dir', { dir });
  }
});

document.querySelectorAll('.dpad-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const [dx, dy] = btn.dataset.dir.split(',').map(Number);
    socket.emit('dir', { dir: [dx, dy] });
  });
});

restartBtn.addEventListener('click', () => {
  socket.emit('restart', {});
  showScreen('game');
  deadBanner.classList.add('hidden');
  particles = [];
  setTimeout(resizeCanvas, 50);
});

// ── Socket events ─────────────────────────────────────────────────────────────
socket.on('joined', data => {
  myId    = data.player_id;
  myColor = data.color;
  gridW   = data.grid[0];
  gridH   = data.grid[1];
  hudRoom.textContent = `Room: ${data.room_id.replace('room_', '#')}`;
  lastState = data.state;
  resizeCanvas();
  render();
});

socket.on('countdown', data => {
  hudCountdown.textContent = data.count;
  hudCountdown.classList.remove('hidden');
});

socket.on('game_start', () => {
  hudCountdown.classList.add('hidden');
  deadBanner.classList.add('hidden');
});

socket.on('state', data => {
  lastState = data;
  const me = data.players[myId];
  if (me && !me.alive) deadBanner.classList.remove('hidden');
  updateScoreboard(data.players);
});

socket.on('game_over', data => {
  goTitle.textContent = '🏆 WINNER!';
  if (data.winner === 'Nobody') goTitle.textContent = '💀 DRAW';
  goWinner.textContent = data.winner !== 'Nobody'
    ? `${data.winner} wins!`
    : 'Everyone died!';

  goScores.innerHTML = '';
  const sorted = Object.entries(data.scores).sort((a,b) => b[1]-a[1]);
  sorted.forEach(([name, score]) => {
    const row = document.createElement('div');
    row.className = 'go-score-row';
    // find color from last state
    let color = '#aaa';
    if (lastState) {
      const p = Object.values(lastState.players).find(p => p.name === name);
      if (p) color = p.color;
    }
    row.innerHTML = `
      <span class="sname"><span class="sdot" style="background:${color}"></span>${name}</span>
      <span class="sval">${score} pts</span>`;
    goScores.appendChild(row);
  });

  setTimeout(() => showScreen('gameover'), 600);
});

socket.on('player_joined', data => {
  // could show a toast — skip for brevity
});

// ── Scoreboard ────────────────────────────────────────────────────────────────
function updateScoreboard(players) {
  scoreboard.innerHTML = '';
  Object.values(players)
    .sort((a,b) => b.score - a.score)
    .forEach(p => {
      const chip = document.createElement('div');
      chip.className = 'score-chip' + (p.alive ? '' : ' dead');
      chip.innerHTML = `
        <span class="score-dot" style="background:${p.color}"></span>
        <span>${p.name}</span>
        <span style="color:${p.color};margin-left:4px">${p.score}</span>`;
      scoreboard.appendChild(chip);
    });
}

// ── Render ────────────────────────────────────────────────────────────────────
function render() {
  animFrame = requestAnimationFrame(render);
  if (lastState) drawState(lastState);
  drawParticles();
}

function drawState(state) {
  const C = cellSize;
  const W = canvas.width;
  const H = canvas.height;

  // Background grid
  ctx.fillStyle = '#050a0e';
  ctx.fillRect(0, 0, W, H);

  ctx.strokeStyle = '#0d2030';
  ctx.lineWidth = .5;
  for (let x = 0; x <= gridW; x++) {
    ctx.beginPath(); ctx.moveTo(x*C, 0); ctx.lineTo(x*C, H); ctx.stroke();
  }
  for (let y = 0; y <= gridH; y++) {
    ctx.beginPath(); ctx.moveTo(0, y*C); ctx.lineTo(W, y*C); ctx.stroke();
  }

  // Food
  state.food.forEach(([fx, fy]) => {
    const cx = fx * C + C/2;
    const cy = fy * C + C/2;
    const r  = C * .38 + Math.sin(Date.now()*0.005 + fx) * C * .06;
    // glow
    const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, r * 2);
    g.addColorStop(0, '#ffcc0099');
    g.addColorStop(1, 'transparent');
    ctx.fillStyle = g;
    ctx.fillRect(cx - r*2, cy - r*2, r*4, r*4);
    // pellet
    ctx.fillStyle = '#ffcc00';
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI*2);
    ctx.fill();
    ctx.fillStyle = '#fff8';
    ctx.beginPath();
    ctx.arc(cx - r*.25, cy - r*.25, r*.3, 0, Math.PI*2);
    ctx.fill();
  });

  // Snakes
  Object.values(state.players).forEach(p => {
    if (!p.body || p.body.length === 0) return;
    const alpha = p.alive ? 1 : .3;
    ctx.globalAlpha = alpha;

    p.body.forEach(([bx, by], i) => {
      const pad = i === 0 ? 1 : 2;
      const x = bx * C + pad;
      const y = by * C + pad;
      const s = C - pad*2;

      if (i === 0) {
        // Head — brighter
        ctx.fillStyle = p.color;
        ctx.shadowColor = p.color;
        ctx.shadowBlur = 12;
        ctx.fillRect(x, y, s, s);
        ctx.shadowBlur = 0;
        // Eyes
        const eyeR = Math.max(1.5, C * .12);
        ctx.fillStyle = '#050a0e';
        ctx.beginPath(); ctx.arc(x + s*.3, y + s*.35, eyeR, 0, Math.PI*2); ctx.fill();
        ctx.beginPath(); ctx.arc(x + s*.7, y + s*.35, eyeR, 0, Math.PI*2); ctx.fill();
        ctx.fillStyle = '#fff';
        ctx.beginPath(); ctx.arc(x + s*.3 + eyeR*.3, y + s*.35 - eyeR*.2, eyeR*.4, 0, Math.PI*2); ctx.fill();
        ctx.beginPath(); ctx.arc(x + s*.7 + eyeR*.3, y + s*.35 - eyeR*.2, eyeR*.4, 0, Math.PI*2); ctx.fill();
      } else {
        // Body — gradient fade toward tail
        const t = i / p.body.length;
        ctx.fillStyle = hexAlpha(p.color, 1 - t * .55);
        ctx.fillRect(x, y, s, s);
      }
    });

    ctx.globalAlpha = 1;
  });
}

// ── Particles ─────────────────────────────────────────────────────────────────
function spawnParticles(x, y, color, n = 8) {
  for (let i = 0; i < n; i++) {
    const angle = Math.random() * Math.PI * 2;
    const speed = 1 + Math.random() * 3;
    particles.push({
      x: x * cellSize + cellSize/2,
      y: y * cellSize + cellSize/2,
      vx: Math.cos(angle) * speed,
      vy: Math.sin(angle) * speed,
      life: 1,
      color,
      r: 2 + Math.random() * 3,
    });
  }
}

function drawParticles() {
  particles = particles.filter(p => p.life > 0);
  particles.forEach(p => {
    p.x += p.vx; p.y += p.vy;
    p.life -= .03;
    ctx.globalAlpha = p.life;
    ctx.fillStyle = p.color;
    ctx.beginPath();
    ctx.arc(p.x, p.y, p.r, 0, Math.PI*2);
    ctx.fill();
  });
  ctx.globalAlpha = 1;
}

// ── Utils ─────────────────────────────────────────────────────────────────────
function hexAlpha(hex, a) {
  const r = parseInt(hex.slice(1,3),16);
  const g = parseInt(hex.slice(3,5),16);
  const b = parseInt(hex.slice(5,7),16);
  return `rgba(${r},${g},${b},${a})`;
}

// ── Init ──────────────────────────────────────────────────────────────────────
showScreen('lobby');
nameInput.focus();