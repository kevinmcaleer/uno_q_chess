# Chess camera for the Arduino UNO Q

A USB webcam looks down on a real chess board. The UNO Q's Linux side watches
the board, works out each move, keeps track of the game, and plays against you
using Stockfish.

## What is Stockfish?

Stockfish is a free, open-source chess engine: a program that, given a chess
position, works out a good move. It is one of the strongest chess programs in
the world, but it has a "Skill Level" setting (0 to 20) so it can play like a
beginner too. It runs happily on the UNO Q's Linux side (`apt install
stockfish`). This app uses it for two things: choosing the computer's moves,
and giving you hints if you ask for them.

## How it works

1. **Calibration (once).** You mark the four corners of the board in the
   camera image. The app uses that to "straighten" every frame into a
   top-down 8x8 grid, so it knows which pixels belong to which square.
2. **Waiting for stillness.** The app waits until the image stops changing
   (your hand has left the board) before it looks at anything.
3. **Which squares changed?** It compares the settled board with the last
   settled board and scores how much each of the 64 squares changed.
4. **Which legal move explains that?** The app always knows the position
   (the game starts from the normal starting position), so it asks
   python-chess for every legal move and picks the one whose squares
   changed while the rest of the board stayed quiet. Castling (4 squares),
   en passant and promotion (assumed queen) are handled.
5. **Computer's turn.** Stockfish picks a move. The app says it out loud (if
   `espeak-ng` is installed), prints it, and saves `last_move.png` with an
   arrow on the board. You make the move for it; the app checks you moved
   the right piece and asks you to fix it if not.

Because of step 4, the app never needs to recognise *what* a piece is, so
ordinary pieces work. Special printed pieces just make it more reliable.

## Repository layout

| Folder | What's in it |
|---|---|
| `/` (top level) | The Python app that runs on the UNO Q (see Files below) |
| [`board/`](board/) | Printable board PDFs (A4 and Letter, 50 mm squares) and `make_board.py` to regenerate them |
| `chess_board_pdf.*` (top level) | Kev's own board design (OmniGraffle source and PDF) |
| [`pieces/`](pieces/README.md) | Low, wide 3D-printable pieces with symbols on top: OpenSCAD source and STLs |
| [`coins/`](coins/README.md) | Flat 15 mm coins for small boards (squares under 20 mm), with PrusaSlicer MMU3 project files |

## Files

| File | What it does |
|---|---|
| `calibrate.py` | Mark the board corners, writes `calibration.json` |
| `vision.py` | Camera, board straightening, per-square change scores |
| `detector.py` | Picks the legal move that matches the changed squares |
| `engine.py` | Stockfish wrapper (play a move, give a hint) |
| `announce.py` | Describes moves in words, speaks them, draws the arrow |
| `main.py` | The game loop |
| `test_detector.py` | Offline test: fake camera images of 600+ moves |

## Setup on the UNO Q

Connect the webcam (and a keyboard/screen if you want the click-to-calibrate
window) through a USB-C hub. Then on the UNO Q:

```bash
sudo apt install stockfish espeak-ng
python3 -m venv ~/chess && source ~/chess/bin/activate
pip install -r requirements.txt     # swap in opencv-python if you want windows
python3 test_detector.py            # sanity check, no camera needed
```

Mount the camera as directly above the board as you can, with even light and
no strong shadows. Then:

```bash
python3 calibrate.py                # or --snapshot / --corners when headless
python3 main.py                     # you play white
python3 main.py --colour black --skill 3 --hints
```

If moves are missed, raise the light level or lower `--change-threshold`.
If the wrong move is read, raise `--min-fit`. After three misses the app
lets you type the move (e.g. `e2e4`) so the game can carry on.

## 3D-printable pieces that read well from above

Ready-to-print files and a print guide are in [`pieces/`](pieces/README.md). The ideas behind them:


- **Low and wide.** Short pieces (about 25 to 30 mm tall) with a flat top
  covering about 70% of the square. Tall pieces lean into neighbouring
  squares in the camera image unless the camera is exactly overhead.
- **Strong colour contrast.** Pick filament colours that differ clearly from
  *both* board square colours, e.g. a green/cream board with red and black
  pieces. Plain white pieces on light squares are the hardest case.
- **A symbol on top.** Emboss or inlay (filament swap at a layer) a simple
  shape: king = cross, queen = ring of dots, rook = square, bishop =
  diagonal slash, knight = "L", pawn = single dot. This makes captures (one
  piece replacing another) change the square's look much more.
- **Later upgrade:** a small ArUco marker printed on top of each piece would
  let the app recognise every piece directly, so it could pick up a game
  from any position, not only from the start.

## Status and next steps

- The move detector passes the offline test (604 moves from simulated,
  angled, noisy camera images, including castling, en passant, captures and
  promotion). The Stockfish wrapper was checked against a real Stockfish.
- **Not yet tried on a real UNO Q with a real camera.** Expect to tune the
  two thresholds for your lighting.
- Ideas: show the computer's move on the UNO Q's LED matrix or a small web
  page, auto-detect the board corners, choose under-promotion pieces, and
  save games as PGN files.
