"""Camera capture, board calibration and per-square change detection."""
import json
import time

import cv2
import numpy as np

WARP_SIZE = 800                 # warped board is WARP_SIZE x WARP_SIZE pixels
SQ = WARP_SIZE // 8             # pixels per square
INNER = 0.6                     # only compare the middle 60% of each square


def load_calibration(path="calibration.json"):
    with open(path) as f:
        data = json.load(f)
    return np.array(data["homography"], dtype=np.float32)


def homography_from_corners(corners):
    """corners: image pixel positions of the outer corners of a8, h8, h1, a1
    (in that order). Returns a matrix that warps the board to a square image
    with a8 top-left and h1 bottom-right."""
    src = np.array(corners, dtype=np.float32)
    dst = np.array([[0, 0], [WARP_SIZE, 0], [WARP_SIZE, WARP_SIZE], [0, WARP_SIZE]],
                   dtype=np.float32)
    return cv2.getPerspectiveTransform(src, dst)


def warp(frame, H):
    return cv2.warpPerspective(frame, H, (WARP_SIZE, WARP_SIZE))


def square_rect(square):
    """Pixel rect (x0, y0, x1, y1) of the inner part of a python-chess square."""
    f, r = square % 8, square // 8
    x, y = f * SQ, (7 - r) * SQ
    m = int(SQ * (1 - INNER) / 2)
    return x + m, y + m, x + SQ - m, y + SQ - m


def change_scores(before, after):
    """Mean colour difference per square between two warped board images.
    Returns a list of 64 floats indexed by python-chess square number."""
    a = cv2.GaussianBlur(cv2.cvtColor(before, cv2.COLOR_BGR2LAB), (5, 5), 0).astype(np.int16)
    b = cv2.GaussianBlur(cv2.cvtColor(after, cv2.COLOR_BGR2LAB), (5, 5), 0).astype(np.int16)
    diff = np.abs(a - b).sum(axis=2)
    scores = []
    for sq in range(64):
        x0, y0, x1, y1 = square_rect(sq)
        scores.append(float(diff[y0:y1, x0:x1].mean()))
    return scores


class Camera:
    def __init__(self, index=0, H=None, width=1280, height=720):
        self.cap = cv2.VideoCapture(index)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        if not self.cap.isOpened():
            raise RuntimeError(f"Could not open camera {index}")
        self.H = H

    def frame(self):
        ok, img = self.cap.read()
        if not ok:
            raise RuntimeError("Camera read failed")
        return img

    def board(self):
        return warp(self.frame(), self.H)

    def wait_until_still(self, still_frames=8, motion_threshold=4.0):
        """Block until the board image stops changing (hands are out of the way)
        and return that settled, warped image."""
        prev = self.board()
        calm = 0
        while True:
            time.sleep(0.1)
            cur = self.board()
            motion = max(change_scores(prev, cur))
            calm = calm + 1 if motion < motion_threshold else 0
            prev = cur
            if calm >= still_frames:
                return cur

    def wait_for_board_change(self, reference, change_threshold, **kw):
        """Wait until the board has settled into a state that differs from
        `reference` on at least one square."""
        while True:
            settled = self.wait_until_still(**kw)
            if max(change_scores(reference, settled)) > change_threshold:
                return settled
