"""Checks the board counts as still with a noisy webcam whose exposure keeps
drifting, and doesn't while a hand is over it.

  python3 test_still.py
"""
import threading
import time

import chess
import cv2
import numpy as np

from test_detector import CORNERS, render
from vision import BoardCamera, homography_from_corners


class NoisyCamera:
    """The start position with fresh sensor noise every frame, brightness
    wandering up and down (auto-exposure), and optionally a hand."""

    def __init__(self, noise=8.0, flicker=12.0):
        self.base = render(chess.Board()).astype(np.float32)
        self.noise, self.flicker = noise, flicker
        self.rng = np.random.default_rng(1)
        self.t = 0
        self.hand = False

    def capture(self):
        time.sleep(0.03)
        self.t += 1
        gain = 1 + self.flicker / 100 * np.sin(self.t / 3)
        img = self.base * gain + self.rng.normal(0, self.noise, self.base.shape)
        if self.hand:                                  # a hand sweeping across the board
            x = 400 + 40 * (self.t % 12)
            cv2.circle(img, (x, 380), 90, (120, 150, 190), -1)
        return np.clip(img, 0, 255).astype(np.uint8)


def settle_time(cam, timeout=8):
    result = {}

    def run():
        start = time.monotonic()
        cam.wait_until_still()
        result["t"] = time.monotonic() - start

    th = threading.Thread(target=run, daemon=True)
    th.start()
    th.join(timeout)
    return result.get("t")


def main():
    for noise, flicker in ((4, 0), (8, 0), (8, 12), (12, 20)):
        physical = NoisyCamera(noise, flicker)
        cam = BoardCamera(physical, homography_from_corners(CORNERS))
        t = settle_time(cam)
        print(f"noise {noise:2d}, exposure drift ±{flicker:2d}%: "
              + (f"settled in {t:.1f} s" if t else "never settled"))
        assert t is not None and t < 3, "a still board should settle"

    physical = NoisyCamera(8, 12)
    physical.hand = True
    cam = BoardCamera(physical, homography_from_corners(CORNERS))
    t = settle_time(cam, timeout=4)
    print("hand over the board: " + ("settled (wrong)" if t else "kept waiting (right)"))
    assert t is None, "a moving hand must not count as still"
    print("All stillness checks passed")


if __name__ == "__main__":
    main()
