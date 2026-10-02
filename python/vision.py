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
    """Return (homography, corners), or (None, None) if the board isn't
    calibrated yet."""
    try:
        with open(path) as f:
            data = json.load(f)
    except FileNotFoundError:
        return None, None
    return np.array(data["homography"], dtype=np.float32), data["corners"]


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


def square_means(board_img):
    """Average LAB colour of the inner part of each square: 64x3 floats."""
    lab = cv2.cvtColor(board_img, cv2.COLOR_BGR2LAB).astype(np.float32)
    out = np.empty((64, 3), np.float32)
    for sq in range(64):
        x0, y0, x1, y1 = square_rect(sq)
        out[sq] = lab[y0:y1, x0:x1].reshape(-1, 3).mean(axis=0)
    return out


def motion(before, after):
    """How much the board moved between two warped images: the largest change
    in any square's average colour, after removing the change the whole board
    shares (exposure or white balance, fitted as gain and offset per colour
    channel). Near 0 for a still board, however noisy the camera; a hand or a
    moving piece gives tens."""
    a, b = square_means(before), square_means(after)
    resid = np.empty_like(a)
    for ch in range(3):
        x, y = a[:, ch], b[:, ch]
        keep = np.ones(64, bool)
        for _ in range(2):            # refit without the squares a hand or piece changed
            if np.ptp(x[keep]) > 1:
                gain, offset = np.polyfit(x[keep], y[keep], 1)
            else:
                gain, offset = 1.0, float(np.median(y - x))
            resid[:, ch] = y - (gain * x + offset)
            keep = np.abs(resid[:, ch]) <= np.sort(np.abs(resid[:, ch]))[47]
    return float(np.abs(resid).sum(axis=1).max())


def occupancy_mismatches(board_img, pieces):
    """Squares where the camera disagrees with the tracked position.

    pieces: {square: True for a white piece, False for black} that should be
    on the board. Each square is scored by how different it looks from an
    empty square of its colour right now (average colour, and how busy it
    is). The cut-off between "looks empty" and "looks occupied" sits halfway
    between the typical empty square and the typical tracked piece of that
    colour on that square colour (a white piece on a light square looks much
    less different than a black one), so it adapts to the lighting and the
    pieces. Returns (looks_occupied_but_empty, looks_empty_but_occupied)."""
    lab = cv2.cvtColor(board_img, cv2.COLOR_BGR2LAB).astype(np.float32)
    mean, busy = np.empty((64, 3), np.float32), np.empty(64, np.float32)
    for sq in range(64):
        x0, y0, x1, y1 = square_rect(sq)
        patch = lab[y0:y1, x0:x1].reshape(-1, 3)
        mean[sq], busy[sq] = patch.mean(axis=0), patch.std(axis=0).sum()
    extra, missing = [], []
    for parity in (0, 1):                      # 0: dark squares, 1: light squares
        squares = [sq for sq in range(64) if (sq % 8 + sq // 8) % 2 == parity]
        empty = [sq for sq in squares if sq not in pieces]
        if len(empty) < 3:
            continue                           # too few empty squares to compare with
        m, b = np.median(mean[empty], axis=0), np.median(busy[empty])
        score = {sq: float(np.abs(mean[sq] - m).sum() + max(0.0, busy[sq] - b)) for sq in squares}
        empty_typ = float(np.median([score[sq] for sq in empty]))
        cuts = {}
        for colour in (True, False):
            group = [score[sq] for sq in squares if pieces.get(sq) is colour]
            if group:
                cuts[colour] = max((empty_typ + float(np.median(group))) / 2, empty_typ + 8)
        # a piece appearing where there should be none: the easier-to-see colour
        # would be obvious, so judge by the harder one (the lowest cut)
        new_cut = min(cuts.values()) if cuts else empty_typ + 15
        for sq in squares:
            if sq in pieces:
                if score[sq] < cuts[pieces[sq]]:
                    missing.append(sq)
            elif score[sq] > new_cut:
                extra.append(sq)
    return sorted(extra), sorted(missing)


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

    def wait_until_still(self, check=lambda: None, still_frames=8, motion_threshold=8.0):
        """Block until the board image stops changing (hands are out of the way)
        and return that settled, warped image.

        Motion is the change in each square's average colour, not pixel by
        pixel, so webcam noise averages out. A change shared by the whole board
        (auto-exposure or white balance drifting) is taken off first, so only a
        hand or a piece moving on some squares counts."""
        prev = self.board()
        calm = 0
        self.motion = None
        while True:
            check()
            time.sleep(0.1)
            cur = self.board()
            self.motion = motion(prev, cur)
            calm = calm + 1 if self.motion < motion_threshold else 0
            prev = cur
            if calm >= still_frames:
                return cur

    def wait_for_board_change(self, reference, change_threshold, check=lambda: None, **kw):
        """Wait until the board has settled into a state that differs from
        `reference` on at least one square (beyond any whole-board lighting change)."""
        while True:
            settled = self.wait_until_still(check, **kw)
            scores = change_scores(reference, settled)
            if max(scores) - float(np.median(scores)) > change_threshold:
                return settled
