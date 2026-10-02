"""Camera capture, board calibration and per-square change detection."""
import json
import threading
import time

import cv2
import numpy as np

WARP_SIZE = 800                 # warped board is WARP_SIZE x WARP_SIZE pixels
SQ = WARP_SIZE // 8             # pixels per square
INNER = 0.6                     # only compare the middle 60% of each square


def load_calibration(path):
    """Return the saved homography, or None if the board isn't calibrated yet."""
    try:
        with open(path) as f:
            data = json.load(f)
    except FileNotFoundError:
        return None
    return np.array(data["homography"], dtype=np.float32)


def save_calibration(path, corners):
    """corners: a8, h8, h1, a1 pixel positions in the camera image."""
    H = homography_from_corners(corners)
    with open(path, "w") as f:
        json.dump({"corners": corners, "homography": H.tolist()}, f, indent=2)
    return H


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


def draw_grid(board_img):
    """Straightened board with the 8x8 grid on it, to check calibration."""
    img = board_img.copy()
    for i in range(9):
        cv2.line(img, (i * SQ, 0), (i * SQ, WARP_SIZE), (0, 255, 0), 1)
        cv2.line(img, (0, i * SQ), (WARP_SIZE, i * SQ), (0, 255, 0), 1)
    cv2.putText(img, "a8", (5, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
    return img


class BoardCamera:
    """Keeps the latest frame from an App Lab Camera (or anything with a
    capture() method returning a BGR image) and waits for the board to settle.

    The wait methods call `check()` on every frame so the game can interrupt
    them (new game, typed move)."""

    def __init__(self, camera, H=None):
        self.camera = camera
        self.H = H
        self._latest = None
        self._seq = 0
        self._cond = threading.Condition()
        threading.Thread(target=self._capture_loop, daemon=True).start()

    def _capture_loop(self):
        while True:
            try:
                img = self.camera.capture()
            except Exception:
                img = None
            if img is None:
                time.sleep(0.05)
                continue
            with self._cond:
                self._latest = img
                self._seq += 1
                self._cond.notify_all()

    def latest(self):
        """Most recent frame, or None if the camera hasn't produced one yet."""
        with self._cond:
            return self._latest

    def frame(self, timeout=5.0):
        """Wait for a frame newer than the last one returned by this call."""
        with self._cond:
            seq = self._seq
            if not self._cond.wait_for(lambda: self._seq > seq, timeout):
                raise RuntimeError("No frames from the camera")
            return self._latest

    def board(self):
        return warp(self.frame(), self.H)

    def wait_until_still(self, check=lambda: None, still_frames=8, motion_threshold=4.0):
        """Block until the board image stops changing (hands are out of the way)
        and return that settled, warped image."""
        prev = self.board()
        calm = 0
        while True:
            check()
            time.sleep(0.1)
            cur = self.board()
            motion = max(change_scores(prev, cur))
            calm = calm + 1 if motion < motion_threshold else 0
            prev = cur
            if calm >= still_frames:
                return cur

    def wait_for_board_change(self, reference, change_threshold, check=lambda: None, **kw):
        """Wait until the board has settled into a state that differs from
        `reference` on at least one square."""
        while True:
            settled = self.wait_until_still(check, **kw)
            if max(change_scores(reference, settled)) > change_threshold:
                return settled
