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
  refreshBoardImage();
});

ui.on_message('say', (m) => {
  const li = document.createElement('li');
  li.textContent = m.text;
  $('#log').prepend(li);
  if ($('#speak').checked && 'speechSynthesis' in window) {
    speechSynthesis.speak(new SpeechSynthesisUtterance(m.text));
  }
});

// ---- board drawing ---------------------------------------------------------

function squareName(file, rank) { return 'abcdefgh'[file] + (rank + 1); }

function drawBoard(s) {
  const rows = s.fen.split(' ')[0].split('/');           // rank 8 first
  const pieces = {};
  rows.forEach((row, i) => {
    let file = 0;
    for (const ch of row) {
      if (/\d/.test(ch)) { file += Number(ch); continue; }
      pieces[squareName(file, 7 - i)] = ch;
      file += 1;
    }
  });
  const mark = (uci) => (uci ? [uci.slice(0, 2), uci.slice(2, 4)] : []);
  const last = mark(s.last_move);
  const expected = mark(s.expected);
  const flip = s.human === 'black';
  const board = $('#board');
  board.innerHTML = '';
  for (let r = 0; r < 8; r++) {
    for (let f = 0; f < 8; f++) {
      const file = flip ? 7 - f : f;
      const rank = flip ? r : 7 - r;
      const name = squareName(file, rank);
      const sq = document.createElement('div');
      sq.className = 'sq ' + ((file + rank) % 2 ? 'light' : 'dark');
      if (expected.includes(name)) sq.classList.add('expected');
      else if (last.includes(name)) sq.classList.add('last');
      const p = pieces[name];
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
      board.appendChild(sq);
    }
  }
}

// ---- controls --------------------------------------------------------------

$('#new-game').addEventListener('submit', (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  ui.send_message('new_game', {
    colour: f.get('colour'),
    skill: Number(f.get('skill')),
    hints: f.get('hints') === 'on',
    change_threshold: Number(f.get('change_threshold')),
    min_fit: Number(f.get('min_fit')),
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

function refreshBoardImage() { $('#board-img').src = 'board.jpg?t=' + Date.now(); }

document.querySelectorAll('.tabs button').forEach((btn) => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tabs button').forEach((b) => b.classList.toggle('active', b === btn));
    const view = btn.dataset.view;
    for (const v of ['board', 'live', 'calibrate']) $('#view-' + v).classList.toggle('hidden', v !== view);
    $('#live-img').src = view === 'live' ? 'live' : '';            // only stream while visible
    if (view === 'board') refreshBoardImage();
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
  setTimeout(refreshBoardImage, 500);
});
window.addEventListener('resize', drawCalibration);
