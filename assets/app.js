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
    if (view === 'calibrate') { resetCorners(); takeSnapshot(); }
  });
});

// ---- calibration: click the outer corners of a8, h8, h1, a1 ------------------

const LABELS = ['a8', 'h8', 'h1', 'a1'];
let corners = [];

function takeSnapshot() { $('#snap').src = 'snapshot.jpg?t=' + Date.now(); }

function resetCorners() { corners = []; drawCorners(); }

function drawCorners() {
  const img = $('#snap');
  const svg = $('#calib-marks');
  svg.setAttribute('viewBox', `0 0 ${img.naturalWidth || 1} ${img.naturalHeight || 1}`);
  const r = (img.naturalWidth || 640) / 120;
  let html = '';
  if (corners.length > 1) {
    const pts = corners.map((c) => c.join(',')).join(' ');
    html += `<polygon points="${pts}" fill="rgb(0 129 132 / 0.15)" stroke="#00c2c7" stroke-width="${r / 2}" />`;
  }
  corners.forEach((c, i) => {
    html += `<circle cx="${c[0]}" cy="${c[1]}" r="${r}" fill="#e4572e" />`;
    html += `<text x="${c[0] + r * 1.5}" y="${c[1] - r * 1.5}" fill="#e4572e" font-size="${r * 3}" font-weight="bold">${LABELS[i]}</text>`;
  });
  svg.innerHTML = html;
  $('#calib-hint').innerHTML = corners.length < 4
    ? `Click the outer corner of <b>${LABELS[corners.length]}</b>.`
    : 'All four corners marked. Save, then check the straightened board.';
  $('#calib-save').disabled = corners.length !== 4;
}

$('#snap').addEventListener('load', drawCorners);
$('#snap').addEventListener('click', (e) => {
  if (corners.length >= 4) return;
  const img = e.target;
  const rect = img.getBoundingClientRect();
  const x = ((e.clientX - rect.left) / rect.width) * img.naturalWidth;
  const y = ((e.clientY - rect.top) / rect.height) * img.naturalHeight;
  corners.push([Math.round(x), Math.round(y)]);
  drawCorners();
});
$('#calib-reset').addEventListener('click', resetCorners);
$('#calib-refresh').addEventListener('click', takeSnapshot);
$('#calib-save').addEventListener('click', () => {
  ui.send_message('calibrate', { corners });
  document.querySelector('.tabs button[data-view=board]').click();
  setTimeout(refreshBoardImage, 500);
});
