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

from engine import Engine, find_local
from game import Game
import stockfish_install
from vision import BoardCamera, load_calibration, save_calibration

DATA_DIR = "/app/data" if os.path.isdir("/app") else os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(DATA_DIR, exist_ok=True)
CALIBRATION = os.path.join(DATA_DIR, "calibration.json")

logger = Logger("ChessCamera")
ui = WebUI()
camera = Camera(resolution=(1280, 720), fps=10)     # first USB camera found
camera.start()
cam = BoardCamera(camera, load_calibration(CALIBRATION))

log = []                                            # recent spoken messages, for new page loads


def say(text):
    logger.info(text)
    log.append(text)
    del log[:-30]
    try:
        ui.send_message("say", {"text": text})
    except Exception:
        pass


def send_state(state=None):
    try:
        ui.send_message("state", state or game.state())
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


# ---- web page -> app ------------------------------------------------------

def on_connect(client):
    send_state()
    for text in log[-10:]:
        ui.send_message("say", {"text": text})


def on_new_game(client, data):
    game.request_new_game(**{k: v for k, v in (data or {}).items()
                             if k in ("colour", "skill", "hints", "change_threshold", "min_fit")})


def on_typed_move(client, data):
    game.request_typed_move(str(data.get("move", "")))


def on_hint(client, data):
    game.request_hint()


def on_calibrate(client, data):
    corners = [(int(round(x)), int(round(y))) for x, y in data["corners"]]
    cam.H = save_calibration(CALIBRATION, corners)
    game.calibrate_preview()
    say("Calibration saved. Check the grid lines up with the squares.")
    send_state()


ui.on_connect(on_connect)
ui.on_message("new_game", on_new_game)
ui.on_message("typed_move", on_typed_move)
ui.on_message("hint", on_hint)
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


def live():
    def frames():
        while True:
            img = cam.latest()
            if img is not None:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg(img, 70) + b"\r\n"
            time.sleep(0.2)
    return StreamingResponse(frames(), media_type="multipart/x-mixed-replace; boundary=frame")


ui.expose_api("GET", "/snapshot.jpg", snapshot)
ui.expose_api("GET", "/board.jpg", board_image)
ui.expose_api("GET", "/live", live)

threading.Thread(target=game.run, daemon=True).start()
show_move(None)

App.run()
