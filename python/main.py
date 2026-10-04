"""Chess camera: play Stockfish on a real board watched by a USB webcam.

Open the app's web page (http://<UNO-Q-IP>:7000) to calibrate the board,
start a game, see the computer's moves and ask for hints. The computer's
last move is also shown on the UNO Q's LED matrix.
"""
import json
import os
import threading
import time

import chess
import cv2
import numpy as np
from fastapi.responses import Response, StreamingResponse

from arduino.app_bricks.web_ui import WebUI
from arduino.app_peripherals.camera import Camera
from arduino.app_utils import App, Bridge, Frame, Logger

from announce import describe
from autocal import alignment, find_board
from engine import Engine, find_local
from game import TUNING_DEFAULTS, Game
import lessons
from speech import Speaker
import stockfish_install
from vision import (WARP_SIZE, BoardCamera, change_scores, load_calibration, motion_of_means,
                    occupancy_mismatches,
                    save_calibration, square_means)

DATA_DIR = "/app/data" if os.path.isdir("/app") else os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(DATA_DIR, exist_ok=True)
CALIBRATION = os.path.join(DATA_DIR, "calibration.json")

logger = Logger("ChessCamera")
ui = WebUI()
camera = Camera(resolution=(1280, 720), fps=15)     # first USB camera found; 15 fps for smooth live video
camera.start()
H, corners = load_calibration(CALIBRATION)
cam = BoardCamera(camera, H, corners)               # corners: for adjusting them on the page
cam.alignment, cam.find_board = alignment, find_board   # re-align if the board gets nudged

log = []                                            # recent spoken messages, for new page loads

speaker = Speaker()                                 # the board's own speaker (see the README)
board_voice = True                                  # speak on the board's speaker when it's there


def say(text):
    """Show a message on the page and speak it: on the board's speaker if
    that's on and working, otherwise the page reads it out itself."""
    logger.info(text)
    log.append(text)
    del log[:-30]
    on_board = board_voice and speaker.say(text)
    try:
        ui.send_message("say", {"text": text, "board": on_board})
    except Exception:
        pass


def voice_state():
    return {"on": board_voice, "status": speaker.status()}


def send_voice(state=None):
    try:
        ui.send_message("voice", state or voice_state())
    except Exception:
        pass


def watch_voice():
    """Tell the page when the board's speaker comes and goes."""
    last = None
    while True:
        state = voice_state()
        if state != last:
            send_voice(state)
            last = state
        time.sleep(10)


def send_state(state=None):
    state = dict(state or game.state(), corners=cam.corners)
    try:
        ui.send_message("state", state)
    except Exception:
        pass


def show_move(move):
    """Light the from and to squares of the computer's move on the 8x13 LED
    matrix (columns 0-7 are files a-h, row 0 is rank 8)."""
    arr = np.zeros((8, 13), dtype=np.uint8)
    if move is not None:
        for sq, level in ((move.from_square, 3), (move.to_square, 7)):
            arr[7 - chess.square_rank(sq), chess.square_file(sq)] = level
    try:
        Bridge.call("draw", Frame(arr).to_board_bytes())
    except Exception as e:
        logger.warning(f"LED matrix not updated: {e}")


def make_engine(skill, think, on_wait=None):
    """Stockfish can't be apt-installed in App Lab's container, so the first
    game downloads it into data/ (needs internet once)."""
    path = find_local()
    if not path:
        if on_wait and not os.path.exists(os.path.join(DATA_DIR, "stockfish")):
            on_wait()
        path = stockfish_install.install(DATA_DIR)
    return Engine(skill=skill, think_time=think, path=path)


game = Game(cam, make_engine, say, send_state, show_move)


def on_realign(corners):
    save_calibration(CALIBRATION, corners)
    say("The board moved, so I've lined the grid up with it again.")
    send_state()


cam.on_realign = on_realign


# ---- lessons ------------------------------------------------------------------

tutor = lessons.Runner()


def send_lesson():
    try:
        ui.send_message("lesson", tutor.state())
    except Exception:
        pass


def lesson_moved(move):
    """A lesson move read from the real board (called by the game loop)."""
    ok, message = tutor.try_move(move)
    after_move(ok, message)
    return ok


def after_move(ok, message):
    if ok and not tutor.finished:
        say(message + " " + tutor.step["text"])
    elif ok:
        say(message + " That's the end of this lesson. Well done!")
    else:
        say(message)
    send_lesson()
    if ok:
        sync_board()


def sync_board():
    """In real-board mode, have the camera watch for the current step's move."""
    if not tutor.on_board:
        return
    if tutor.wants_move:
        game.request_lesson(tutor.board, lesson_moved)
    else:
        game.request_idle("Lesson: read the page, then press Next." if not tutor.finished
                          else "Lesson finished. Pick another, or start a game.")


def on_lesson_open(client, data):
    if str((data or {}).get("id")) not in lessons.BY_ID:
        return
    tutor.open(str(data.get("id")))
    send_lesson()
    say(f"{tutor.lesson['title']}. {tutor.step['text']}")
    sync_board()


def on_lesson_nav(client, data):
    action = (data or {}).get("action")
    if action == "next":
        tutor.next()
    elif action == "back":
        tutor.go(tutor.i - 1)
    elif action == "restart":
        tutor.go(0)
    send_lesson()
    if tutor.lesson and not tutor.finished:
        say(tutor.step["text"])
    sync_board()


def on_lesson_move(client, data):
    if tutor.lesson:
        after_move(*tutor.try_move(str((data or {}).get("move", ""))))


def on_lesson_answer(client, data):
    move = tutor.answer()
    if move:
        say("Try " + describe(tutor.board, move) + ".")
        ui.send_message("lesson_answer", {"move": move.uci()})


def on_lesson_board(client, data):
    tutor.on_board = bool((data or {}).get("on"))
    send_lesson()
    if tutor.on_board:
        if game.cam.H is None:
            say("Calibrate the board first to use it for lessons.")
        sync_board()
    else:
        game.request_idle("Lessons on screen. Start a new game to play on the board.")


def on_lesson_set_up(client, data):
    game.request_set_up()


# ---- web page -> app ------------------------------------------------------

def on_connect(client):
    send_state()
    ui.send_message("lessons", {"lessons": lessons.catalogue()})
    send_lesson()
    ui.send_message("occupancy", occupancy)
    ui.send_message("tuning", game.tuning)
    for text in log[-10:]:
        ui.send_message("say", {"text": text, "replay": True})
    send_voice()


# ---- tuning (sliders on the page), kept in data/tuning.json ---------------

TUNING_FILE = os.path.join(DATA_DIR, "tuning.json")


def load_tuning():
    try:
        with open(TUNING_FILE) as f:
            game.set_tuning(**json.load(f))
    except (OSError, ValueError, TypeError):
        game.set_tuning()


def on_tuning(client, data):
    data = data or {}
    if data.get("reset"):
        game.set_tuning(**TUNING_DEFAULTS)
    else:
        game.set_tuning(**{k: v for k, v in data.items() if k in TUNING_DEFAULTS})
    try:
        with open(TUNING_FILE, "w") as f:
            json.dump(game.tuning, f, indent=2)
    except OSError as e:
        logger.warning(f"Tuning not saved: {e}")
    ui.send_message("tuning", game.tuning)


readout_until = 0.0                                 # send the change readout until then
readout_ref = None                                  # board to compare with outside a game


def on_readout(client, data):
    global readout_until
    readout_until = time.monotonic() + 12           # the page asks again every 5 s while shown


def on_new_game(client, data):
    tutor.on_board = False                          # the board is for the game now
    send_lesson()
    game.request_new_game(**{k: v for k, v in (data or {}).items()
                             if k in ("colour", "skill", "hints", "coach")})


def on_typed_move(client, data):
    game.request_typed_move(str(data.get("move", "")))


def on_board_voice(client, data):
    global board_voice
    board_voice = bool((data or {}).get("on"))
    send_voice()
    if board_voice:
        say("I'll talk through the board's speaker.")


def on_hint(client, data):
    game.request_hint()


def on_calibrate(client, data):
    corners = [(round(float(x), 2), round(float(y), 2)) for x, y in data["corners"]]
    save_calibration(CALIBRATION, corners)
    cam.set_calibration(corners)
    game.calibrate_preview()
    say("Calibration saved. Check the grid lines up with the squares.")
    send_state()


def on_find_board(client, data):
    """Find the board from its squares (in the background: it can take a few
    seconds on the UNO Q). With corners, snap those to the squares."""
    approx = (data or {}).get("corners")

    def work():
        frame = cam.latest()
        found = find_board(frame, approx) if frame is not None else None
        if found:
            message = ("Found the board. Check the grid and that a1 (shaded) is in the right "
                       "corner, use Rotate labels if not, then save.")
        elif approx:
            message = ("Couldn't snap to the squares. Make sure the whole board is in view and "
                       "evenly lit, or adjust the corners by hand.")
        else:
            message = ("Couldn't find the board. It works best on an empty board; you can also "
                       "click the corners roughly and press Snap to squares.")
        ui.send_message("board_found", {"corners": [list(c) for c in found] if found else None,
                                        "message": message})

    threading.Thread(target=work, daemon=True).start()


ui.on_connect(on_connect)
ui.on_message("find_board", on_find_board)
ui.on_message("new_game", on_new_game)
ui.on_message("typed_move", on_typed_move)
ui.on_message("hint", on_hint)
ui.on_message("board_voice", on_board_voice)
ui.on_message("calibrate", on_calibrate)
ui.on_message("tuning", on_tuning)
ui.on_message("readout", on_readout)
ui.on_message("lesson_open", on_lesson_open)
ui.on_message("lesson_nav", on_lesson_nav)
ui.on_message("lesson_move", on_lesson_move)
ui.on_message("lesson_answer", on_lesson_answer)
ui.on_message("lesson_board", on_lesson_board)
ui.on_message("lesson_set_up", on_lesson_set_up)


# ---- images for the web page ---------------------------------------------

def jpeg(img, quality=80):
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return buf.tobytes() if ok else b""


def snapshot():
    """Full camera frame, used for clicking the board corners."""
    img = cam.latest()
    if img is None:
        return Response(status_code=503)
    return Response(jpeg(img, 90), media_type="image/jpeg", headers={"Cache-Control": "no-store"})


def board_image():
    """Straightened board with the grid and the computer's move drawn on it."""
    if game.board_image is None:
        return Response(status_code=404)
    return Response(jpeg(game.board_image), media_type="image/jpeg",
                    headers={"Cache-Control": "no-store"})


LIVE_SIZE = 560                                     # straightened live video, pixels square


class Feed:
    """One JPEG video feed shared by every open page: each camera frame is
    made into a JPEG once, however many browsers are watching, and not at all
    when none are."""

    def __init__(self, make):
        self.make = make                                # camera frame -> JPEG bytes, or None
        self.viewers = 0
        self.jpeg, self.seq = None, 0
        self.cond = threading.Condition()
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while True:
            with self.cond:
                self.cond.wait_for(lambda: self.viewers > 0)
            try:
                data = self.make(cam.frame())           # waits for the next camera frame
            except Exception:
                data = None
            if data is None:
                time.sleep(0.5)
                continue
            with self.cond:
                self.jpeg, self.seq = data, self.seq + 1
                self.cond.notify_all()

    def stream(self):
        def frames():
            with self.cond:
                self.viewers += 1
                self.cond.notify_all()
            try:
                seq = 0
                while True:
                    with self.cond:
                        if not self.cond.wait_for(lambda: self.seq > seq, timeout=5):
                            continue
                        seq, data = self.seq, self.jpeg
                    yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + data + b"\r\n"
            finally:
                with self.cond:
                    self.viewers -= 1
        return StreamingResponse(frames(), media_type="multipart/x-mixed-replace; boundary=frame")


def straightened_jpeg(img):
    """The straightened board for the live video, with the grid and the
    computer's move. Warped straight to the video size, which is cheaper than
    straightening at full size."""
    H = cam.H
    if H is None:
        return None
    k = LIVE_SIZE / WARP_SIZE
    top = cv2.warpPerspective(img, np.diag([k, k, 1.0]).astype(np.float32) @ H, (LIVE_SIZE, LIVE_SIZE))
    step = LIVE_SIZE / 8
    for i in range(9):
        p = int(round(i * step))
        cv2.line(top, (p, 0), (p, LIVE_SIZE), (0, 255, 0), 1)
        cv2.line(top, (0, p), (LIVE_SIZE, p), (0, 255, 0), 1)
    move = game.expected
    if move:
        ends = [(int((chess.square_file(sq) + 0.5) * step),
                 int((7.5 - chess.square_rank(sq)) * step)) for sq in (move.from_square, move.to_square)]
        cv2.arrowedLine(top, ends[0], ends[1], (0, 0, 255), 8, tipLength=0.25)
    return jpeg(top, 75)


board_feed = Feed(straightened_jpeg)
camera_feed = Feed(lambda img: jpeg(img, 70))


def board_live():
    return board_feed.stream()


def live():
    return camera_feed.stream()


ui.expose_api("GET", "/snapshot.jpg", snapshot)
ui.expose_api("GET", "/board.jpg", board_image)
ui.expose_api("GET", "/live", live)
ui.expose_api("GET", "/board_live", board_live)


# ---- does the camera agree with the tracked position? ----------------------

occupancy = {"extra": [], "missing": []}


def watch_occupancy():
    """Once a second, while the board is still, compare which squares look
    occupied with the tracked position. A disagreement has to last two checks
    in a row (so a move the game hasn't read yet doesn't flash up)."""
    global occupancy, readout_ref
    prev = pending = None
    while True:
        time.sleep(1)
        try:
            if cam.H is None:
                continue
            means = square_means(cam.board_small())      # cheap: is anything moving?
            moving = motion_of_means(prev, means) if prev is not None else None
            still = moving is not None and moving < game.tuning["still"]
            prev = means
            if time.monotonic() < readout_until:
                top = cam.board()
                # in a game: changes since the last settled board; otherwise
                # since the readout was switched on
                if game.settings is None:
                    if readout_ref is None:
                        readout_ref = top
                    ref = readout_ref
                else:
                    ref = game.reference
                scores = change_scores(ref, top) if ref is not None else None
                ui.send_message("readout", {"scores": scores, "motion": moving})
            else:
                readout_ref = None
            if not still:
                continue
            top = cam.board()
            pieces = {sq: p.color for sq, p in game.board.copy().piece_map().items()}
            extra, missing = occupancy_mismatches(top, pieces, game.tuning["marks"])
            found = {"extra": [chess.square_name(s) for s in extra],
                     "missing": [chess.square_name(s) for s in missing]}
            if found == pending and found != occupancy:
                occupancy = found
                ui.send_message("occupancy", occupancy)
            pending = found
        except Exception as e:
            logger.warning(f"Occupancy check failed: {e}")


threading.Thread(target=watch_occupancy, daemon=True).start()
threading.Thread(target=watch_voice, daemon=True).start()

load_tuning()
threading.Thread(target=game.run, daemon=True).start()
show_move(None)

App.run()
