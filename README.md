# Chess camera for the Arduino UNO Q

An [Arduino App Lab](https://docs.arduino.cc/software/app-lab/) app. A USB
webcam looks down on a real chess board. The UNO Q's Linux side watches the
board, works out each move, keeps track of the game, and plays against you
using Stockfish. You control it from a web page on your phone or computer.

## What is Stockfish?

Stockfish is a free, open-source chess engine: a program that, given a chess
position, works out a good move. It is one of the strongest chess programs in
the world, but it has a "Skill Level" setting (0 to 20) so it can play like a
beginner too. App Lab apps can't `apt install` anything, so the app
downloads Debian's Stockfish package itself on the first game and keeps the
engine in `data/stockfish`. This app uses it for two things: choosing the computer's moves,
and giving you hints if you ask for them.

## How it works

1. **Calibration (once).** On the web page you click the four corners of
   the board in a camera snapshot. The app uses that to "straighten" every frame into a
   top-down 8x8 grid, so it knows which pixels belong to which square.
2. **Waiting for stillness.** The app waits until the image stops changing
   (your hand has left the board) before it looks at anything. It compares
   each square's average colour, so webcam noise averages out, and ignores
   brightness changes the whole board shares, so auto-exposure doesn't count
   as movement.
3. **Which squares changed?** It compares the settled board with the last
   settled board and scores how much each of the 64 squares changed.
4. **Which legal move explains that?** The app always knows the position
   (the game starts from the normal starting position), so it asks
   python-chess for every legal move and picks the one whose squares
   changed while the rest of the board stayed quiet. Castling (4 squares),
   en passant and promotion (assumed queen) are handled. It also checks
   which squares look occupied: the move's starting square must now look
   empty, and a piece you knock while moving (but that's still on its
   square) doesn't count against the reading. The app tells you to centre it (at most two pieces at a time, each only once). If nearly every piece changes at once, the board itself slid, so it lines the grid up again instead.
5. **Computer's turn.** Stockfish picks a move. The web page shows it
   (and reads it aloud if you like), the LED matrix lights its from and to
   squares, and you make the move for it; the app checks you moved the
   right piece and asks you to fix it if not.

Because of step 4, the app never needs to recognise *what* a piece is, so
ordinary pieces work. Special printed pieces just make it more reliable.

If the board itself gets nudged during a game, the app notices the next
time the board is still (the grid no longer lines up with the squares),
finds the board again from its squares and moves the grid onto it, keeping
which corner is a1. It says so, and saves the new calibration.

The *Straightened board* tab shows the board as live video (at the
camera's 15 fps), straightened so you can watch hands move pieces, with a
small badge in each square for the piece the app thinks is there. Once a
second, while nothing is moving, it also checks which squares look occupied:
a square with no piece seen where one should be is outlined in red, and an
unexpected piece in yellow, so you can spot when the board and the game
have drifted apart.

## Repository layout

The repository is an App Lab app: `app.yaml`, `python/`, `assets/`,
and `sketch/` are what App Lab uses. The rest is printable stuff.

| Path | What's in it |
|---|---|
| `app.yaml` | App manifest: name, icon, and the bricks it uses (`arduino:web_ui`) |
| `python/` | The app that runs on the UNO Q's Linux side (see Files below) |
| `assets/` | The web page (served by the Web UI brick on port 7000) |
| `sketch/` | Microcontroller sketch: draws the computer's move on the LED matrix |
| [`board/`](board/) | Printable board PDFs (A4 and Letter, 50 mm squares) and `make_board.py` to regenerate them |
| `chess_board_pdf.*` | Kev's own board design (OmniGraffle source and PDF) |
| [`pieces/`](pieces/README.md) | Low, wide 3D-printable pieces with symbols on top: OpenSCAD source and STLs |
| [`coins/`](coins/README.md) | Flat 15 mm coins for small boards (squares under 20 mm), with PrusaSlicer MMU3 project files |

## Files in `python/`

| File | What it does |
|---|---|
| `main.py` | App Lab entry point: camera, web page messages and images, LED matrix |
| `game.py` | The game loop (runs in its own thread) |
| `vision.py` | Board straightening, per-square change scores, waiting for stillness |
| `detector.py` | Picks the legal move that matches the changed squares |
| `engine.py` | Talks UCI to Stockfish |
| `speech.py` | Speaks messages on the board's speaker (espeak-ng, sent to the board's sound server) |
| `stockfish_install.py` | Downloads the Stockfish binary from the Debian mirror on the first run (no apt or root needed) |
| `announce.py` | Describes moves in words, draws the arrow on the board image |
| `explain.py` | Tutor: says why a move is good or bad (hanging pieces, mates, forks, pins, missed captures) and grades it with Stockfish |
| `test_detector.py` | Offline test: fake camera images of 600+ moves |
| `autocal.py` | Finds the board corners from the chequerboard pattern |
| `test_game.py` | Offline test of the whole game loop with a fake camera and real Stockfish |
| `test_autocal.py` | Offline test of automatic calibration on near, far and rotated boards |
| `test_still.py` | Offline test of the stillness check with webcam noise, exposure drift and a hand |
| `test_occupancy.py` | Offline test of spotting missing and unexpected pieces |
| `test_nudge.py` | Offline test of reading moves when a neighbouring piece gets knocked |
| `test_realign.py` | Offline test of the grid following the board when it's nudged mid-game |
| `test_explain.py` | Offline test of the move explanations on classic positions |

## Running it on the UNO Q

1. Copy this repository into App Lab's apps folder on the UNO Q, e.g.
   `git clone https://github.com/kevinmcaleer/uno_q_chess ~/ArduinoApps/chess-camera`
   (or create a new app in App Lab and copy these folders into it).
2. Plug the USB webcam into the UNO Q (through a USB-C hub). Mount it as
   directly above the board as you can, with even light and no strong shadows.
3. Open the app in App Lab and press **Run**. The first game needs internet:
   the app downloads Stockfish (about 30 MB) into `data/`. The page says
   "Downloading Stockfish" until it's ready.
4. Open `http://<UNO-Q-IP>:7000` on your phone or computer.
5. **Calibrate:** in the Camera panel, choose *Calibrate*.
   - **Find board automatically** looks for the chequerboard itself. It works
     best on an empty board (the pieces hide some square corners); with the
     pieces set up it usually works too, unless the board is small in the picture.
   - Or click the outer corners of a8, h8, h1 and a1 roughly (within about a
     third of a square) and press **Snap to squares** to line them up exactly.
   - Zoom in with the slider, drag a corner to move it (a magnifier shows
     while you drag), or tap one and nudge it with the arrow keys.
   - The cyan grid should sit on the squares with a1 (shaded) in the right
     corner; **Rotate labels** turns them a quarter turn if not.

   Then *Save calibration*. Calibration is saved in `data/calibration.json`
   and kept between runs; opening *Calibrate* again shows the saved corners
   so you can fine-tune them. Redo it if the camera moves.
6. Set up the pieces, pick your colour and the computer's skill, and press
   **Start new game**.

During the game the page shows the position, the move list and what the app
says (tick *Read messages aloud* to hear it). The computer's move is outlined
in red on the board and drawn as an arrow on the camera view. *Hint* asks
Stockfish for a move for you. If a move can't be read, you can type it
(`e2e4` or `Nf3`) and then make it on the board.

With *Coach me* ticked (the default), the app checks each of your moves with
Stockfish and tells you when it was a mistake and why ("That lets me
checkmate with queen takes on f7. Better was pawn to g6"), or what was good
about it ("Great move: forking the king and rook"). Ordinary moves get no
comment. The computer also says why it played its move when there's a clear
reason.

The LED matrix shows the computer's last move from White's side: the left
8x8 columns are the board (a-h left to right, rank 8 at the top), the
from-square dim and the to-square bright.

## Talking through a speaker on the board

The UNO Q doesn't play sound over HDMI, but the app can talk through a
Bluetooth speaker (or a USB speaker on the hub). The speech is made inside
the app by espeak-ng, which comes as a pip package (`espeakng-loader`), so
nothing is apt-installed. App Lab's container can't reach the board's
sound system directly, so the app sends the audio to the board's sound
server (PipeWire or PulseAudio, which is where a Bluetooth speaker plays)
over its "simple protocol" TCP port, 4712. That port needs turning on once.

On the UNO Q (a terminal, or `ssh arduino@<UNO-Q-IP>`), first check the
speaker plays:

```bash
bluetoothctl devices Connected    # the speaker should be listed
pactl list short sinks            # it shows as bluez_output....
pactl set-default-sink <the bluez_output name>
paplay /usr/share/sounds/alsa/Front_Center.wav    # you should hear "front centre"
```

If `pactl` isn't found, or no `bluez_output` sink appears, install the
sound server with Bluetooth support and reconnect the speaker:

```bash
sudo apt install pipewire-pulse wireplumber libspa-0.2-bluetooth pulseaudio-utils
systemctl --user enable --now pipewire pipewire-pulse wireplumber
bluetoothctl connect <speaker MAC>
```

Then open the port the app talks to, and keep it open after a reboot:

```bash
mkdir -p ~/.config/pipewire/pipewire-pulse.conf.d
cat > ~/.config/pipewire/pipewire-pulse.conf.d/chess-speaker.conf <<'CONF'
pulse.cmd = [
  { cmd = "load-module" args = "module-simple-protocol-tcp rate=22050 format=s16le channels=1 playback=true record=false port=4712 listen=0.0.0.0" flags = [ "nofail" ] }
]
CONF
systemctl --user restart pipewire-pulse
sudo loginctl enable-linger arduino     # sound server runs even when nobody is logged in
```

(To try it without saving anything: `pactl load-module module-simple-protocol-tcp
rate=22050 format=s16le channels=1 playback=true record=false port=4712 listen=0.0.0.0`.)
Anything on your network can play sound through that port, so close it
(`rm` the file and restart pipewire-pulse) if that matters to you.

*Speak through the board's speaker* on the page is on by default. While
the board can't speak (the port isn't open, or the speaker is off) the page
says so and reads messages aloud itself, if *Read messages aloud* is ticked.
The voice is espeak-ng's British English; `SPEAKER_VOICE`, `SPEAKER_SPEED`
(words per minute), `SPEAKER_HOST` and `SPEAKER_PORT` environment variables
change it.

## Testing without the hardware

On any computer with Python 3:

```bash
sudo apt install stockfish        # or brew install stockfish
python3 -m venv .venv && source .venv/bin/activate
pip install chess numpy opencv-python-headless
cd python
python3 test_detector.py          # move detector, 604 simulated moves
python3 test_game.py              # whole game loop against real Stockfish
python3 test_autocal.py           # automatic calibration
python3 test_still.py             # stillness check with a noisy, flickering camera
python3 test_occupancy.py         # spotting missing and unexpected pieces
python3 test_nudge.py             # reading moves when a neighbouring piece gets knocked
python3 test_realign.py           # the grid following the board when it's nudged
python3 test_explain.py           # tutor explanations (hanging pieces, forks, mates...)
python3 test_speech.py            # speaking on the board's speaker (pip install espeakng-loader)
```

## Tuning

If moves are missed, raise the light level or lower the change threshold;
if the wrong move is read, raise the minimum fit. Both are under *Tuning*
in the New game panel and apply from the next game. If
the app never says "Board ready", something in view keeps changing part of
the board (a shadow, a flickering light on one side): raise `motion_threshold`
in `vision.py` (default 8; a hand over the board measures 20 or more).

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
  promotion), and the game loop passes `test_game.py` against a real
  Stockfish, run directly and over TCP. `stockfish_install.py` was checked by
  downloading and running Stockfish from a package mirror as a normal user.
- **Not yet tried on a real UNO Q with a real camera**, so the App Lab parts
  (camera, Web UI, Stockfish download, LED matrix) are untested on hardware.
  Expect to tune the thresholds for your lighting.
- Ideas: auto-detect the board corners, choose under-promotion pieces, and
  save games as PGN files.
