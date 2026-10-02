"""Chess camera: play Stockfish on a real board watched by a USB webcam.

Open the app's web page (http://<UNO-Q-IP>:7000) to calibrate the board,
start a game, see the computer's moves and ask for hints. The computer's
last move is also shown on the UNO Q's LED matrix.
"""
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

from autocal import alignment, find_board
from engine import Engine, find_local
from game import Game
from speech import Speaker
import stockfish_install
from vision import (WARP_SIZE, BoardCamera, load_calibration, motion, occupancy_mismatches,
                    save_calibration, warp)

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


# ---- web page -> app ------------------------------------------------------

def on_connect(client):
    send_state()
    ui.send_message("occupancy", occupancy)
    for text in log[-10:]:
        ui.send_message("say", {"text": text, "replay": True})
    send_voice()


def on_new_game(client, data):
    game.request_new_game(**{k: v for k, v in (data or {}).items()
                             if k in ("colour", "skill", "hints", "change_threshold", "min_fit")})


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


def board_live():
    """The straightened board as live video, at the camera's frame rate, with
    the grid and the computer's move. Each frame is warped straight to the
    video size, which is cheaper than straightening at full size."""
    scale = LIVE_SIZE / WARP_SIZE
    S = np.diag([scale, scale, 1.0]).astype(np.float32)

    def frames():
        while True:
            try:
                img = cam.frame()                   # waits for the next camera frame
            except RuntimeError:
                continue
            H = cam.H
            if H is None:
                time.sleep(0.5)
                continue
            top = cv2.warpPerspective(img, S @ H, (LIVE_SIZE, LIVE_SIZE))
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
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg(top, 75) + b"\r\n"
    return StreamingResponse(frames(), media_type="multipart/x-mixed-replace; boundary=frame")


def live():
    def frames():
        while True:
            try:
                img = cam.frame()                   # every camera frame
            except RuntimeError:
                continue
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg(img, 70) + b"\r\n"
    return StreamingResponse(frames(), media_type="multipart/x-mixed-replace; boundary=frame")


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
    global occupancy
    prev = pending = None
    while True:
        time.sleep(1)
        try:
            img, H = cam.latest(), cam.H
            if img is None or H is None:
                continue
            top = warp(img, H)
            still = prev is not None and motion(prev, top) < 8
            prev = top
            if not still:
                continue
            pieces = {sq: p.color for sq, p in game.board.copy().piece_map().items()}
            extra, missing = occupancy_mismatches(top, pieces)
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

threading.Thread(target=game.run, daemon=True).start()
show_move(None)

App.run()
