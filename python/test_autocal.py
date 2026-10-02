"""Offline test of automatic calibration: renders the board at different
sizes and angles (empty, and set up for a game) and checks the detected
corners land within a pixel or two of the true ones, with a8 in the right place.

  python3 test_autocal.py
"""
import chess
import cv2
import numpy as np

from autocal import find_board
from vision import SQ, WARP_SIZE, homography_from_corners

rng = np.random.default_rng(5)


def render(board, corners, size=(1280, 720), noise=3):
    top = np.zeros((WARP_SIZE, WARP_SIZE, 3), np.uint8)
    for sq in chess.SQUARES:
        f, r = chess.square_file(sq), chess.square_rank(sq)
        x, y = f * SQ, (7 - r) * SQ
        top[y:y + SQ, x:x + SQ] = (181, 217, 240) if (f + r) % 2 else (99, 136, 181)
        p = board.piece_at(sq)
        if p:
            cv2.circle(top, (x + SQ // 2, y + SQ // 2), 36,
                       (235, 235, 235) if p.color else (40, 40, 40), -1)
    H = homography_from_corners(corners)
    bg = np.full((size[1], size[0], 3), 90, np.uint8)
    cam = cv2.warpPerspective(top, np.linalg.inv(H), size, dst=bg, borderMode=cv2.BORDER_TRANSPARENT)
    return np.clip(cam + rng.normal(0, noise, cam.shape), 0, 255).astype(np.uint8)


CASES = {
    "near, angled": [(380, 90), (930, 110), (1010, 650), (300, 630)],
    "far, small": [(560, 260), (720, 265), (735, 420), (548, 415)],
    "rotated 90 (a8 bottom-left)": [(400, 650), (380, 120), (900, 100), (930, 640)],
    "far, tilted": [(600, 300), (700, 290), (730, 390), (590, 400)],
}


def main(seeds=4):
    global rng
    worst, misses, runs = 0, 0, 0
    for name, truth in CASES.items():
        side = np.linalg.norm(np.subtract(truth[0], truth[1])) / 8
        for setup in ("empty", "start"):
            board = chess.Board(None) if setup == "empty" else chess.Board()
            for seed in range(seeds):
                rng = np.random.default_rng(seed)
                img = render(board, truth)
                # rough clicks, up to 1/3 of a square out, snapped to the squares
                rough = [(x + rng.uniform(-1, 1) * side / 3, y + rng.uniform(-1, 1) * side / 3)
                         for x, y in truth]
                for how, approx in (("clicks", rough), ("auto", None)):
                    if how == "auto" and setup == "empty" and "rotated" in name:
                        continue     # an empty board can't say where White sits
                    runs += 1
                    found = find_board(img, approx)
                    if found is None:
                        # allowed: no clicks, pieces on a small board. Never a wrong answer.
                        assert how == "auto" and setup == "start" and "far" in name, (name, setup, how)
                        misses += 1
                        continue
                    err = np.abs(np.subtract(found, truth)).max()
                    assert err < 1.5, (name, setup, how, seed, err)
                    worst = max(worst, err)
            print(f"{name:28s} {setup:5s} ok")
    print(f"\nAll {runs - misses} of {runs} boards found within {worst:.2f} px "
          f"({misses} small boards with pieces need rough clicks first)")


if __name__ == "__main__":
    main()
