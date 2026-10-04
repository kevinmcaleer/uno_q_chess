const ui = new WebUI();
const $ = (sel) => document.querySelector(sel);

const GLYPH = { k: '♚', q: '♛', r: '♜', b: '♝', n: '♞', p: '♟' };
let state = null;

ui.on_connect(() => { $('#connection').textContent = 'connected'; $('#connection').classList.remove('off'); });
ui.on_disconnect(() => { $('#connection').textContent = 'offline'; $('#connection').classList.add('off'); });

ui.on_message('state', (s) => {
  state = s;
  $('#status').textContent = s.status;
  drawBoard(s);
  $('#moves').innerHTML = '';
  for (let i = 0; i < s.moves.length; i += 2) {
    const li = document.createElement('li');
    li.textContent = s.moves[i] + (s.moves[i + 1] ? '  ' + s.moves[i + 1] : '');
    $('#moves').appendChild(li);
  }
  drawOverlay();
});

let occupancy = { extra: [], missing: [] };
ui.on_message('occupancy', (o) => { occupancy = o; drawOverlay(); });

ui.on_message('say', (m) => {
  const li = document.createElement('li');
  li.textContent = m.text;
  $('#log').prepend(li);
  // The board speaks it when its speaker is on and working; otherwise the
  // browser reads it. Old messages replayed on page load aren't read again.
  if (!m.board && !m.replay && $('#speak').checked && 'speechSynthesis' in window) {
    speechSynthesis.speak(new SpeechSynthesisUtterance(m.text));
  }
});

ui.on_message('voice', (v) => {
  $('#board-voice').checked = v.on;
  $('#voice-note').textContent = !v.on || v.status === 'ready' ? ''
    : v.status === 'no voice' ? '(speech failed to load: the browser reads aloud instead)'
    : '(no speaker set up on the board: the browser reads aloud instead)';
});
$('#board-voice').addEventListener('change', (e) => ui.send_message('board_voice', { on: e.target.checked }));

// ---- board drawing ---------------------------------------------------------

function squareName(file, rank) { return 'abcdefgh'[file] + (rank + 1); }

function piecesFromFen(fen) {
  const rows = fen.split(' ')[0].split('/');             // rank 8 first
  const pieces = {};
  rows.forEach((row, i) => {
    let file = 0;
    for (const ch of row) {
      if (/\d/.test(ch)) { file += Number(ch); continue; }
      pieces[squareName(file, 7 - i)] = ch;
      file += 1;
    }
  });
  return pieces;
}

// marks: { squareName: ['class', ...] }; onClick(squareName) makes it clickable.
function renderBoard(board, fen, { flip = false, marks = {}, onClick = null } = {}) {
  const pieces = piecesFromFen(fen);
  board.innerHTML = '';
  for (let r = 0; r < 8; r++) {
    for (let f = 0; f < 8; f++) {
      const file = flip ? 7 - f : f;
      const rank = flip ? r : 7 - r;
      const name = squareName(file, rank);
      const sq = document.createElement('div');
      sq.className = 'sq ' + ((file + rank) % 2 ? 'light' : 'dark');
      for (const c of marks[name] || []) sq.classList.add(c);
      const p = pieces[name];
      // hover a square to see what's on it
      sq.title = p ? `${p === p.toUpperCase() ? 'White' : 'Black'} ${NAMES[p.toLowerCase()]} on ${name}`
                   : `${name}: empty`;
      if (p) {
        const span = document.createElement('span');
        span.textContent = GLYPH[p.toLowerCase()];
        if (p === p.toUpperCase()) span.className = 'w';
        sq.appendChild(span);
      }
      if (f === 0 || r === 7) {
        const c = document.createElement('span');
        c.className = 'coord';
        c.textContent = name;
        sq.appendChild(c);
      }
      if (onClick) sq.addEventListener('click', () => onClick(name));
      board.appendChild(sq);
    }
  }
}

function drawBoard(s) {
  const marks = {};
  const mark = (uci, cls) => { if (uci) for (const n of [uci.slice(0, 2), uci.slice(2, 4)]) marks[n] = [cls]; };
  mark(s.last_move, 'last');
  mark(s.expected, 'expected');
  mark(s.hint, 'hint');
  const flip = s.human === 'black';
  renderBoard($('#board'), s.fen, { flip, marks });
  drawArrows($('#board'), [[s.expected, 'expected'], [s.hint, 'hint']], flip);
}

// Arrows over a board for moves (uci), like the computer's move or a hint.
function drawArrows(board, moves, flip) {
  const svgNS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(svgNS, 'svg');
  svg.setAttribute('viewBox', '0 0 8 8');
  svg.setAttribute('class', 'arrows');
  svg.setAttribute('aria-hidden', 'true');
  const centre = (name) => {
    const f = 'abcdefgh'.indexOf(name[0]), r = Number(name[1]) - 1;
    return flip ? [7.5 - f, r + 0.5] : [f + 0.5, 7.5 - r];
  };
  for (const [uci, cls] of moves) {
    if (!uci) continue;
    const [x1, y1] = centre(uci.slice(0, 2)), [x2, y2] = centre(uci.slice(2, 4));
    const len = Math.hypot(x2 - x1, y2 - y1), ux = (x2 - x1) / len, uy = (y2 - y1) / len;
    const head = 0.35, bx = x2 - ux * head, by = y2 - uy * head;
    const g = document.createElementNS(svgNS, 'g');
    g.setAttribute('class', cls);
    g.setAttribute('opacity', '0.8');
    const line = document.createElementNS(svgNS, 'line');
    for (const [k, v] of Object.entries({ x1, y1, x2: bx, y2: by, 'stroke-width': 0.14, 'stroke-linecap': 'round' }))
      line.setAttribute(k, v);
    const tip = document.createElementNS(svgNS, 'polygon');
    tip.setAttribute('points', [[x2, y2], [bx - uy * 0.22, by + ux * 0.22], [bx + uy * 0.22, by - ux * 0.22]]
      .map((p) => p.join(',')).join(' '));
    g.append(line, tip);
    svg.appendChild(g);
  }
  board.appendChild(svg);
}

// ---- controls --------------------------------------------------------------

$('#new-game').addEventListener('submit', (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  ui.send_message('new_game', {
    colour: f.get('colour'),
    skill: Number(f.get('skill')),
    hints: f.get('hints') === 'on',
    coach: f.get('coach') === 'on',
  });
});
$('#new-game [name=skill]').addEventListener('input', (e) => { $('#skill-out').textContent = e.target.value; });

$('#hint').addEventListener('click', () => ui.send_message('hint', {}));

$('#type-move').addEventListener('submit', (e) => {
  e.preventDefault();
  const move = $('#move').value.trim();
  if (move) ui.send_message('typed_move', { move });
  $('#move').value = '';
});

// ---- camera views ----------------------------------------------------------

// The straightened board streams live while its tab is open. On top, each
// tracked piece gets a small badge in its square's corner, and squares where
// the camera disagrees with the tracked position are outlined.

const NAMES = { k: 'king', q: 'queen', r: 'rook', b: 'bishop', n: 'knight', p: 'pawn' };
let boardView = true;

function updateBoardStream() {
  const calibrated = !!(state && state.calibrated);
  const want = boardView && calibrated ? 'board_live' : '';
  const img = $('#board-img');
  if ((img.getAttribute('src') || '') !== want) {
    if (want) img.src = want; else img.removeAttribute('src');
  }
  $('#board-uncal').classList.toggle('hidden', calibrated);
  $('#board-overlay').classList.toggle('hidden', !calibrated);
}

function drawOverlay() {
  updateBoardStream();
  const svg = $('#board-overlay');
  svg.innerHTML = '';
  if (!state) return;
  const el = (tag, attrs, text) => {
    const e = document.createElementNS(svgNS, tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
    if (text) e.textContent = text;
    svg.appendChild(e);
    return e;
  };
  // the straightened board always has a8 top-left, as the camera sees it
  const xy = (name) => ['abcdefgh'.indexOf(name[0]), 8 - Number(name[1])];
  if ($('#show-pieces').checked) {
    for (const [name, p] of Object.entries(piecesFromFen(state.fen))) {
      const [x, y] = xy(name);
      const white = p === p.toUpperCase();
      el('rect', { x: x + 0.04, y: y + 0.04, width: 0.38, height: 0.38, rx: 0.08,
                   class: white ? 'badge w' : 'badge b' });
      el('text', { x: x + 0.23, y: y + 0.25, class: white ? 'glyph w' : 'glyph b' }, GLYPH[p.toLowerCase()] + '\uFE0E')
        .appendChild(document.createElementNS(svgNS, 'title')).textContent =
          `${white ? 'White' : 'Black'} ${NAMES[p.toLowerCase()]} on ${name}`;
    }
  }
  if (readout && readout.scores) {
    const thr = tuning.change_threshold || 25;
    readout.scores.forEach((v, sq) => {
      const name = 'abcdefgh'[sq % 8] + (Math.floor(sq / 8) + 1);
      const [x, y] = xy(name);
      el('text', { x: x + 0.5, y: y + 0.82, class: 'score' + (v > thr ? ' over' : '') }, String(Math.round(v)));
    });
  }
  $('#readout-note').textContent = readout
    ? `Board movement now: ${readout.motion == null ? '-' : readout.motion.toFixed(1)}` +
      ` (still below ${Math.round(tuning.still || 8)}). Squares in red changed more than ${Math.round(tuning.change_threshold || 25)}.`
    : '';
  for (const [kind, list] of [['missing', occupancy.missing], ['extra', occupancy.extra]]) {
    for (const name of list) {
      const [x, y] = xy(name);
      el('rect', { x: x + 0.05, y: y + 0.05, width: 0.9, height: 0.9, class: 'mismatch ' + kind });
      el('text', { x: x + 0.82, y: y + 0.3, class: 'mismatch-mark' }, '?');
    }
  }
  const parts = [];
  if (occupancy.missing.length) parts.push(`no piece on ${occupancy.missing.join(', ')}`);
  if (occupancy.extra.length) parts.push(`an unexpected piece on ${occupancy.extra.join(', ')}`);
  $('#occupancy-note').textContent = parts.length
    ? `The camera sees ${parts.join(' and ')}. Check the board matches the game.` : '';
}

$('#show-pieces').addEventListener('change', drawOverlay);

// ---- tuning: sliders apply straight away; the readout shows how much each
// square has changed since the last settled board, to see where to set them

let tuning = {};
let readout = null;                       // {scores: [64], motion} while shown

ui.on_message('tuning', (t) => {
  tuning = t;
  document.querySelectorAll('[data-tune]').forEach((input) => {
    const k = input.dataset.tune;
    if (document.activeElement !== input) input.value = t[k];
    $('#out-' + k).textContent = Math.round(t[k]);
  });
  drawOverlay();
});

let tuneTimer = null;
document.querySelectorAll('[data-tune]').forEach((input) => {
  input.addEventListener('input', () => {
    $('#out-' + input.dataset.tune).textContent = input.value;
    clearTimeout(tuneTimer);
    tuneTimer = setTimeout(() => ui.send_message('tuning', { [input.dataset.tune]: Number(input.value) }), 150);
  });
});
$('#tune-reset').addEventListener('click', () => ui.send_message('tuning', { reset: true }));

ui.on_message('readout', (r) => { readout = $('#show-changes').checked ? r : null; drawOverlay(); });
function askReadout() { if ($('#show-changes').checked) ui.send_message('readout', {}); }
$('#show-changes').addEventListener('change', () => {
  if (!$('#show-changes').checked) readout = null;
  askReadout();
  drawOverlay();
});
setInterval(askReadout, 5000);            // the app sends it for a while after each ask

document.querySelectorAll('.tabs button').forEach((btn) => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tabs button').forEach((b) => b.classList.toggle('active', b === btn));
    const view = btn.dataset.view;
    for (const v of ['board', 'live', 'calibrate']) $('#view-' + v).classList.toggle('hidden', v !== view);
    $('#live-img').src = view === 'live' ? 'live' : '';            // only stream while visible
    boardView = view === 'board';
    updateBoardStream();
    btn.closest('.card').classList.toggle('wide', view === 'calibrate');
    if (view === 'calibrate') openCalibration();
  });
});

// ---- calibration ------------------------------------------------------------
// Corners are image pixels of the outer corners of a8, h8, h1, a1. They can be
// clicked, found automatically, snapped to the squares, dragged and nudged.

const LABELS = ['a8', 'h8', 'h1', 'a1'];
const svgNS = 'http://www.w3.org/2000/svg';
let corners = [];
let selected = -1;
let dragging = -1;
let imgW = 1280;
let imgH = 720;
const snapImg = new Image();
let fitOnLoad = false;

function openCalibration() {
  corners = state && state.corners ? state.corners.map((c) => [...c]) : [];
  selected = -1;
  fitOnLoad = true;
  takeSnapshot();
}

function takeSnapshot() {
  snapImg.onload = () => {
    imgW = snapImg.naturalWidth;
    imgH = snapImg.naturalHeight;
    const svg = $('#calib-svg');
    svg.setAttribute('viewBox', `0 0 ${imgW} ${imgH}`);
    const im = $('#calib-img');
    im.setAttribute('width', imgW);
    im.setAttribute('height', imgH);
    im.setAttribute('href', snapImg.src);
    drawCalibration();
    if (fitOnLoad) zoomToBoard();
    fitOnLoad = false;
  };
  snapImg.src = 'snapshot.jpg?t=' + Date.now();
}

function setZoom(z, centre) {
  z = Math.min(6, Math.max(1, z));
  const vp = $('#calib-viewport');
  // keep the middle of the view in the middle while zooming
  const cx = (vp.scrollLeft + vp.clientWidth / 2) / vp.scrollWidth;
  const cy = (vp.scrollTop + vp.clientHeight / 2) / vp.scrollHeight;
  $('#zoom').value = z;
  $('#zoom-out-label').textContent = z + '×';
  $('#calib-svg').style.width = z * 100 + '%';
  const [fx, fy] = centre ? [centre[0] / imgW, centre[1] / imgH] : [cx, cy];
  vp.scrollLeft = fx * vp.scrollWidth - vp.clientWidth / 2;
  vp.scrollTop = fy * vp.scrollHeight - vp.clientHeight / 2;
  drawCalibration();
}

// Zoom so the board fills most of the view, centred.
function zoomToBoard() {
  if (corners.length !== 4) return;
  const xs = corners.map((c) => c[0]);
  const ys = corners.map((c) => c[1]);
  const w = Math.max(...xs) - Math.min(...xs);
  const h = Math.max(...ys) - Math.min(...ys);
  const vp = $('#calib-viewport');
  const fitW = (0.75 * imgW) / w;
  const fitH = (0.75 * 0.7 * window.innerHeight) / ((h * vp.clientWidth) / imgW);
  const z = Math.floor(Math.min(fitW, fitH) * 2) / 2;
  setZoom(z, [(Math.min(...xs) + Math.max(...xs)) / 2, (Math.min(...ys) + Math.max(...ys)) / 2]);
}
function zoom() { return Number($('#zoom').value); }
$('#zoom').addEventListener('input', (e) => setZoom(Number(e.target.value)));
$('#zoom-in').addEventListener('click', () => setZoom(zoom() + 0.5));
$('#zoom-out').addEventListener('click', () => setZoom(zoom() - 0.5));

// Homography from the 8x8 board (0..8, 0..8; a8 at 0,0) to the image.
function homography(c) {
  const src = [[0, 0], [8, 0], [8, 8], [0, 8]];
  const A = [];
  const b = [];
  for (let i = 0; i < 4; i++) {
    const [x, y] = src[i];
    const [u, v] = c[i];
    A.push([x, y, 1, 0, 0, 0, -u * x, -u * y]); b.push(u);
    A.push([0, 0, 0, x, y, 1, -v * x, -v * y]); b.push(v);
  }
  for (let i = 0; i < 8; i++) {                       // Gaussian elimination
    let p = i;
    for (let r = i + 1; r < 8; r++) if (Math.abs(A[r][i]) > Math.abs(A[p][i])) p = r;
    [A[i], A[p]] = [A[p], A[i]]; [b[i], b[p]] = [b[p], b[i]];
    for (let r = 0; r < 8; r++) {
      if (r === i) continue;
      const f = A[r][i] / A[i][i];
      for (let k = i; k < 8; k++) A[r][k] -= f * A[i][k];
      b[r] -= f * b[i];
    }
  }
  const h = b.map((v, i) => v / A[i][i]);
  return (x, y) => {
    const w = h[6] * x + h[7] * y + 1;
    return [(h[0] * x + h[1] * y + h[2]) / w, (h[3] * x + h[4] * y + h[5]) / w];
  };
}

function el(tag, attrs) {
  const e = document.createElementNS(svgNS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  return e;
}

function drawCalibration() {
  const scale = imgW / ($('#calib-svg').clientWidth || imgW);   // image px per screen px
  const grid = $('#calib-grid');
  const handles = $('#calib-handles');
  grid.innerHTML = '';
  handles.innerHTML = '';
  const line = scale * 1.5;
  if (corners.length === 4) {
    const H = homography(corners);
    for (let i = 0; i <= 8; i++) {
      for (const [a, b] of [[[i, 0], [i, 8]], [[0, i], [8, i]]]) {
        const p = H(...a);
        const q = H(...b);
        grid.appendChild(el('line', { x1: p[0], y1: p[1], x2: q[0], y2: q[1], stroke: '#00e5ff',
          'stroke-width': i % 8 ? line : line * 2, opacity: 0.8 }));
      }
    }
    // shade a1 so the orientation is easy to check
    const sq = [[0, 7], [1, 7], [1, 8], [0, 8]].map((p) => H(...p).join(',')).join(' ');
    grid.appendChild(el('polygon', { points: sq, fill: 'rgb(242 193 78 / 0.45)' }));
  } else if (corners.length > 1) {
    grid.appendChild(el('polyline', { points: corners.map((c) => c.join(',')).join(' '),
      fill: 'none', stroke: '#00e5ff', 'stroke-width': line }));
  }
  corners.forEach((c, i) => {
    const g = el('g', { class: 'handle' + (i === selected ? ' selected' : ''), 'data-i': i });
    g.appendChild(el('circle', { cx: c[0], cy: c[1], r: scale * 11, fill: 'rgb(228 87 46 / 0.25)',
      stroke: '#e4572e', 'stroke-width': scale * 2 }));
    g.appendChild(el('circle', { cx: c[0], cy: c[1], r: scale * 1.5, fill: '#e4572e' }));
    const t = el('text', { x: c[0] + scale * 14, y: c[1] - scale * 14, fill: '#fff',
      'font-size': scale * 15, 'font-weight': 'bold', stroke: '#000', 'stroke-width': scale * 0.6 });
    t.textContent = LABELS[i];
    g.appendChild(t);
    handles.appendChild(g);
  });
  $('#calib-hint').innerHTML = corners.length < 4
    ? `Click the outer corner of <b>${LABELS[corners.length]}</b>, or press <b>Find board automatically</b>.`
    : 'Check the grid sits on the squares and a1 (shaded) is in the right place, then save.';
  $('#calib-save').disabled = corners.length !== 4;
  $('#calib-snap').disabled = corners.length !== 4;
  $('#calib-rotate').disabled = corners.length !== 4;
}

function toImage(evt) {
  const svg = $('#calib-svg');
  const pt = svg.createSVGPoint();
  pt.x = evt.clientX;
  pt.y = evt.clientY;
  const p = pt.matrixTransform(svg.getScreenCTM().inverse());
  return [Math.min(imgW, Math.max(0, p.x)), Math.min(imgH, Math.max(0, p.y))];
}

function showLoupe(c) {
  const loupe = $('#loupe');
  if (!c) { loupe.classList.add('hidden'); return; }
  loupe.classList.remove('hidden');
  // keep the magnifier away from the corner being moved
  const rect = $('#calib-svg').getBoundingClientRect();
  const sx = rect.left + (c[0] / imgW) * rect.width;
  loupe.classList.toggle('right', sx - $('#calib-viewport').getBoundingClientRect().left < 220);
  const ctx = loupe.getContext('2d');
  const mag = 6;
  const half = loupe.width / mag / 2;
  ctx.imageSmoothingEnabled = false;
  ctx.fillStyle = '#000';
  ctx.fillRect(0, 0, loupe.width, loupe.height);
  ctx.drawImage(snapImg, c[0] - half, c[1] - half, half * 2, half * 2, 0, 0, loupe.width, loupe.height);
  ctx.strokeStyle = '#e4572e';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(loupe.width / 2, 0); ctx.lineTo(loupe.width / 2, loupe.height);
  ctx.moveTo(0, loupe.height / 2); ctx.lineTo(loupe.width, loupe.height / 2);
  ctx.stroke();
}

$('#calib-svg').addEventListener('pointerdown', (e) => {
  const h = e.target.closest('.handle');
  if (h) {
    dragging = selected = Number(h.dataset.i);
    $('#calib-svg').setPointerCapture(e.pointerId);
    showLoupe(corners[dragging]);
  } else if (corners.length < 4) {
    corners.push(toImage(e));
    selected = corners.length - 1;
  } else {
    selected = -1;
  }
  e.preventDefault();
  drawCalibration();
});
$('#calib-svg').addEventListener('pointermove', (e) => {
  if (dragging < 0) return;
  corners[dragging] = toImage(e);
  showLoupe(corners[dragging]);
  drawCalibration();
});
for (const ev of ['pointerup', 'pointercancel']) {
  $('#calib-svg').addEventListener(ev, () => { dragging = -1; showLoupe(null); });
}

document.addEventListener('keydown', (e) => {
  if (selected < 0 || $('#view-calibrate').classList.contains('hidden')) return;
  if (['INPUT', 'SELECT', 'TEXTAREA'].includes(document.activeElement.tagName)) return;
  const step = e.shiftKey ? 5 : 0.5;
  const d = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] }[e.key];
  if (!d) return;
  e.preventDefault();
  corners[selected] = [corners[selected][0] + d[0], corners[selected][1] + d[1]];
  showLoupe(corners[selected]);
  clearTimeout(window.loupeTimer);
  window.loupeTimer = setTimeout(() => showLoupe(null), 1200);
  drawCalibration();
});

function findBoard(useCorners) {
  $('#calib-hint').textContent = 'Looking for the board... (this can take a little while)';
  for (const id of ['#calib-auto', '#calib-snap']) $(id).disabled = true;
  ui.send_message('find_board', useCorners && corners.length === 4 ? { corners } : {});
}
ui.on_message('board_found', (m) => {
  $('#calib-auto').disabled = false;
  if (m.corners) {
    corners = m.corners;
    selected = -1;
    fitOnLoad = true;
    takeSnapshot();
  }
  drawCalibration();
  $('#calib-hint').textContent = m.message;
});

$('#calib-auto').addEventListener('click', () => findBoard(false));
$('#calib-snap').addEventListener('click', () => findBoard(true));
$('#calib-rotate').addEventListener('click', () => { corners.push(corners.shift()); drawCalibration(); });
$('#calib-reset').addEventListener('click', () => { corners = []; selected = -1; drawCalibration(); });
$('#calib-refresh').addEventListener('click', takeSnapshot);
$('#calib-save').addEventListener('click', () => {
  ui.send_message('calibrate', { corners });
  document.querySelector('.tabs button[data-view=board]').click();
  updateBoardStream();
});
window.addEventListener('resize', drawCalibration);

// ---- lessons ----------------------------------------------------------------
// The app holds the lessons and checks each move; the page shows the current
// step and sends clicked moves. With "Use my real board" the camera reads them.

let lesson = { id: null };
let lessonList = [];
let picked = null;                     // square clicked first, for a two-click move
let answer = null;                     // move shown by Show me

const DONE_KEY = 'chess-lessons-done';
function doneLessons() {
  try { return new Set(JSON.parse(localStorage.getItem(DONE_KEY) || '[]')); } catch { return new Set(); }
}
function markDone(id) {
  const done = doneLessons();
  done.add(id);
  try { localStorage.setItem(DONE_KEY, JSON.stringify([...done])); } catch { /* private mode */ }
}

function showMode(mode) {
  document.querySelectorAll('.modes button').forEach((b) => b.classList.toggle('active', b.dataset.mode === mode));
  document.querySelectorAll('.mode-play').forEach((e) => e.classList.toggle('hidden', mode !== 'play'));
  document.querySelectorAll('.mode-lessons').forEach((e) => e.classList.toggle('hidden', mode !== 'lessons'));
  try { localStorage.setItem('chess-mode', mode); } catch { /* ignore */ }
}
document.querySelectorAll('.modes button').forEach((b) => b.addEventListener('click', () => showMode(b.dataset.mode)));
try { if (localStorage.getItem('chess-mode') === 'lessons') showMode('lessons'); } catch { /* ignore */ }

function drawLessonList() {
  const done = doneLessons();
  const list = $('#lesson-list');
  list.innerHTML = '';
  let section = null;
  let chips = null;
  for (const l of lessonList) {
    if (l.section !== section) {
      section = l.section;
      const h = document.createElement('h3');
      h.textContent = section;
      chips = document.createElement('div');
      chips.className = 'chips';
      list.append(h, chips);
    }
    const b = document.createElement('button');
    b.textContent = l.title;
    if (done.has(l.id)) b.classList.add('done');
    b.addEventListener('click', () => ui.send_message('lesson_open', { id: l.id }));
    chips.appendChild(b);
  }
}

function drawLesson() {
  const open = !!lesson.id;
  $('#lesson').classList.toggle('hidden', !open);
  $('#lesson-list').classList.toggle('hidden', open);
  if (!open) { drawLessonList(); return; }
  if (lesson.finished) markDone(lesson.id);
  $('#lesson-title').textContent = lesson.title;
  $('#lesson-progress').textContent = `Step ${lesson.step + 1} of ${lesson.steps}`;
  $('#lesson-text').textContent = lesson.finished ? 'Lesson complete. Well done!' : lesson.text;
  const fb = $('#lesson-feedback');
  fb.textContent = lesson.feedback;
  fb.className = 'feedback ' + (lesson.feedback.startsWith('Correct') ? 'good' : lesson.feedback ? 'bad' : '');
  const marks = {};
  const add = (name, cls) => { (marks[name] = marks[name] || []).push(cls); };
  for (const n of lesson.show) add(n, 'show');
  if (lesson.last_move) { add(lesson.last_move.slice(0, 2), 'last'); add(lesson.last_move.slice(2, 4), 'last'); }
  if (answer) { add(answer.slice(0, 2), 'expected'); add(answer.slice(2, 4), 'expected'); }
  if (picked) add(picked, 'selected');
  renderBoard($('#lesson-board'), lesson.fen, { marks, onClick: lesson.wants_move ? clickSquare : null });
  $('#lesson-back').disabled = lesson.step === 0;
  $('#lesson-answer').disabled = !lesson.wants_move;
  $('#lesson-next').disabled = lesson.wants_move || lesson.finished;
  $('#lesson-next').textContent = lesson.step + 1 === lesson.steps ? 'Finish' : 'Next';
  $('#lesson-on-board').checked = lesson.on_board;
  $('#lesson-board-tools').classList.toggle('hidden', !(lesson.on_board && lesson.wants_move));
}

function clickSquare(name) {
  const pieces = piecesFromFen(lesson.fen);
  const mine = (p) => p && (p === p.toUpperCase()) === (lesson.turn === 'white');
  if (picked && picked !== name && !mine(pieces[name])) {
    ui.send_message('lesson_move', { move: picked + name });
    picked = null;
  } else {
    picked = pieces[name] && picked !== name ? name : null;
  }
  drawLesson();
}

ui.on_message('lessons', (m) => { lessonList = m.lessons; drawLesson(); });
ui.on_message('lesson', (l) => {
  if (l.id !== lesson.id || l.step !== lesson.step) { picked = null; answer = null; }
  lesson = l;
  drawLesson();
});
ui.on_message('lesson_answer', (m) => { answer = m.move; drawLesson(); });

$('#lesson-close').addEventListener('click', () => { lesson = { id: null }; drawLesson(); });
$('#lesson-back').addEventListener('click', () => ui.send_message('lesson_nav', { action: 'back' }));
$('#lesson-next').addEventListener('click', () => ui.send_message('lesson_nav', { action: 'next' }));
$('#lesson-restart').addEventListener('click', () => ui.send_message('lesson_nav', { action: 'restart' }));
$('#lesson-answer').addEventListener('click', () => ui.send_message('lesson_answer', {}));
$('#lesson-set-up').addEventListener('click', () => ui.send_message('lesson_set_up', {}));
$('#lesson-on-board').addEventListener('change', (e) => ui.send_message('lesson_board', { on: e.target.checked }));
