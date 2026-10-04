"""The light in the room changes while the game waits for a move (a cloud,
a lamp switched on, the webcam's auto-exposure jumping): the board hasn't
changed, so nothing should be said, and the next move must still be read.
A hand left resting over the board gets one "Lots of the board changed"
message, not a new one every second.

  python3 test_lighting.py
"""
import threading
import time

import chess
import cv2
import numpy as np

from game import Game
from test_detector import CORNERS, render
from vision import BoardCamera, homography_from_corners

LOTS = "Lots of the board changed"


class Room:
    """A still board under some lighting, with fresh sensor noise every frame."""

    def __init__(self):
        self.board = chess.Board()
        self.light = (1.0, 0.0)                         # (overall gain, side light)
        self.hand = False
        self.frames = []
        self.n = 0
        self.lock = threading.Lock()
        self._render()

    def _render(self):
        gain, side = self.light
        frames = []
        for _ in range(4):                              # a few, each with its own noise
            img = render(self.board, side_light=side).astype(np.float32) * gain
            if self.hand:
                cv2.ellipse(img, (560, 400), (170, 110), 20, 0, 360, (110, 140, 185), -1)
            frames.append(np.clip(img, 0, 255).astype(np.uint8))
        with self.lock:
            self.frames = frames

    def set(self, light=None, move=None, hand=None):
        if light is not None:
            self.light = light
        if move is not None:
            self.board.push_uci(move)
        if hand is not None:
            self.hand = hand
        self._render()

    def capture(self):
        time.sleep(0.02)
        with self.lock:
            self.n += 1
            return self.frames[self.n % len(self.frames)]


def start_reading(room):
    cam = BoardCamera(room, homography_from_corners(CORNERS))
    said = []
    game = Game(cam, None, say=said.append, on_update=lambda s: None)
    result = {}

    def run():
        result["move"], _ = game._read_move(cam.wait_until_still())
    threading.Thread(target=run, daemon=True).start()
    time.sleep(1.5)                                     # reference taken
    return said, result


def wait_for(cond, timeout):
    end = time.monotonic() + timeout
    while not cond() and time.monotonic() < end:
        time.sleep(0.05)
    return cond()


def main():
    for light in ((0.75, 0.0), (1.25, 0.0), (1.0, 0.4), (0.8, 0.3)):
        room = Room()
        said, result = start_reading(room)
        room.set(light=light)
        time.sleep(6)                                   # several settles under the new light
        quiet = not said
        room.set(move="e2e4")
        read = wait_for(lambda: "move" in result, 10)
        print(f"light x{light[0]:.2f}, {light[1]:.0%} brighter on one side: "
              f"said {said or 'nothing'} while nothing moved; then "
              + (f"read {result['move'].uci()}" if read else "didn't read e2e4"))
        assert quiet, said
        assert read and result["move"].uci() == "e2e4", said

    room = Room()
    said, result = start_reading(room)
    room.set(hand=True)
    time.sleep(7)
    lots = sum(LOTS in t for t in said)
    print(f"hand resting over the board for 7 s: said '{LOTS}' {lots} time(s)")
    assert lots == 1, said
    room.set(hand=False, move="g1f3")
    assert wait_for(lambda: "move" in result, 10) and result["move"].uci() == "g1f3", result
    print("hand taken away and g1f3 played: read g1f3")


if __name__ == "__main__":
    main()
