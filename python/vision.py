"""Camera capture, board calibration and per-square change detection."""
import json
import threading
import time

import cv2
import numpy as np

WARP_SIZE = 800                 # warped board is WARP_SIZE x WARP_SIZE pixels
SQ = WARP_SIZE // 8             # pixels per square
INNER = 0.6                     # only compare the middle 60% of each square
STILL_SIZE = 200                # board size for the (frequent) stillness check


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


def _per_square(img):
    """View of the inner part of every square: (rank 1..8, file a..h, h, w, ...),
    so rank r, file f is python-chess square r * 8 + f. Works at any image
    size that's a multiple of 8."""
    sq = img.shape[0] // 8
    m = int(sq * (1 - INNER) / 2)
    grid = img.reshape(8, sq, 8, sq, *img.shape[2:])[::-1]          # row 0 is rank 8
    return grid[:, m:sq - m, :, m:sq - m].swapaxes(1, 2)


def change_scores(before, after):
    """Mean colour difference per square between two warped board images.
    Returns a list of 64 floats indexed by python-chess square number."""
    a = cv2.GaussianBlur(cv2.cvtColor(before, cv2.COLOR_BGR2LAB), (5, 5), 0).astype(np.int16)
    b = cv2.GaussianBlur(cv2.cvtColor(after, cv2.COLOR_BGR2LAB), (5, 5), 0).astype(np.int16)
    diff = np.abs(a - b).sum(axis=2).astype(np.float32)
    return _per_square(diff).mean(axis=(2, 3)).reshape(64).tolist()


def square_means(board_img):
    """Average LAB colour of the inner part of each square: 64x3 floats."""
    lab = cv2.cvtColor(board_img, cv2.COLOR_BGR2LAB).astype(np.float32)
    return _per_square(lab).mean(axis=(2, 3)).reshape(64, 3)


def motion(before, after):
    """How much the board moved between two warped images: the largest change
    in any square's average colour, after removing the change the whole board
    shares (exposure or white balance, fitted as gain and offset per colour
    channel). Near 0 for a still board, however noisy the camera; a hand or a
    moving piece gives tens."""
    return motion_of_means(square_means(before), square_means(after))


def motion_of_means(a, b):
    """motion() from square_means() of the two images."""
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


def _smooth_fit(values, known, squares):
    """Predict values (n x k) on `squares` from those on the `known` squares
    with a smooth surface across the board (a gentle curve in file and rank),
    so light that falls off across the board, or glare on one side, is
    allowed for. Fitted twice, the second time without the squares that fit
    worst (a piece the game doesn't know about, a shadow)."""
    def design(sqs):
        f = np.array([s % 8 for s in sqs], np.float32) / 7 - 0.5
        r = np.array([s // 8 for s in sqs], np.float32) / 7 - 0.5
        cols = [np.ones_like(f), f, r]
        if len(known) >= 10:
            cols += [f * f, r * r, f * r]
        return np.stack(cols, axis=1)

    known = list(known)
    A, y = design(known), values[known]
    keep = np.ones(len(known), bool)
    for _ in range(2):
        coef, *_ = np.linalg.lstsq(A[keep], y[keep], rcond=None)
        err = np.abs(y - A @ coef).sum(axis=1)
        if keep.sum() > A.shape[1] + 3:
            keep = err <= np.quantile(err, 0.8)
    return design(squares) @ coef


def occupancy_mismatches(board_img, pieces, margin=8.0):
    """Squares where the camera disagrees with the tracked position.

    pieces: {square: True for a white piece, False for black} that should be
    on the board. Each square is scored by how different it looks from an
    empty square of its colour right now (average colour, and how busy it
    is), where "an empty square" is fitted across the board from the squares
    the game says are empty, so uneven light and glare are allowed for.
    The cut-off between "looks empty" and "looks occupied" sits halfway
    between the typical empty square and the typical tracked piece of that
    colour on that square colour (a white piece on a light square looks much
    less different than a black one), so it adapts to the lighting and the
    pieces. margin: the least a square must stand out to count (higher
    shows fewer marks). Returns (looks_occupied_but_empty, looks_empty_but_occupied)."""
    lab = _per_square(cv2.cvtColor(board_img, cv2.COLOR_BGR2LAB).astype(np.float32))
    mean = lab.mean(axis=(2, 3)).reshape(64, 3)
    busy = lab.std(axis=(2, 3)).sum(axis=-1).reshape(64)
    extra, missing = [], []
    for parity in (0, 1):                      # 0: dark squares, 1: light squares
        squares = [sq for sq in range(64) if (sq % 8 + sq // 8) % 2 == parity]
        empty = [sq for sq in squares if sq not in pieces]
        if len(empty) < 5:
            continue                           # too few empty squares to compare with
        m = _smooth_fit(mean, empty, squares)
        b = float(np.median(busy[empty]))
        score = {sq: float(np.abs(mean[sq] - m[i]).sum() + max(0.0, busy[sq] - b))
                 for i, sq in enumerate(squares)}
        empty_typ = float(np.median([score[sq] for sq in empty]))
        cuts = {}
        for colour in (True, False):
            group = [score[sq] for sq in squares if pieces.get(sq) is colour]
            if group:
                cuts[colour] = max((empty_typ + float(np.median(group))) / 2, empty_typ + 8)
        # a piece appearing where there should be none: the easier-to-see colour
        # would be obvious, so judge by the harder one (the lowest cut)
        new_cut = min(cuts.values()) if cuts else empty_typ + 15
        # margin above the default 8 makes both kinds of mark harder to get
        stricter = margin - 8
        for sq in squares:
            if sq in pieces:
                if score[sq] < cuts[pieces[sq]] - stricter:
                    missing.append(sq)
            elif score[sq] > max(new_cut, empty_typ + margin) + max(0.0, stricter):
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

    def __init__(self, camera, H=None, corners=None):
        self.camera = camera
        self.H = H
        self.corners = corners
        # Re-aligning after the board is nudged (set up by main.py):
        # alignment(frame, corners) -> 0..1 and find_board(frame, corners) -> corners or None
        self.alignment = None
        self.find_board = None
        self.on_realign = lambda corners: None
        self.baseline = None            # alignment just after (re)calibrating
        self.motion_threshold = 8.0     # below this the board counts as still
        self.motion = None              # the latest motion measured, for the web page
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

    def board_small(self, size=STILL_SIZE):
        """The straightened board at a small size: plenty for average square
        colours, and far cheaper than the full size."""
        k = size / WARP_SIZE
        return cv2.warpPerspective(self.frame(), np.diag([k, k, 1.0]).astype(np.float32) @ self.H,
                                   (size, size), flags=cv2.INTER_AREA)

    def wait_until_still(self, check=lambda: None, still_frames=8, motion_threshold=None):
        """Block until the board image stops changing (hands are out of the way)
        and return that settled, warped image.

        Motion is the change in each square's average colour, not pixel by
        pixel, so webcam noise averages out. A change shared by the whole board
        (auto-exposure or white balance drifting) is taken off first, so only a
        hand or a piece moving on some squares counts."""
        prev = square_means(self.board_small())
        calm = 0
        while True:
            check()
            time.sleep(0.1)
            cur = square_means(self.board_small())
            self.motion = motion_of_means(prev, cur)
            calm = calm + 1 if self.motion < (motion_threshold or self.motion_threshold) else 0
            prev = cur
            if calm >= still_frames:
                return self.board()

    def set_calibration(self, corners):
        self.corners = corners
        self.H = homography_from_corners(corners)
        self.baseline = None

    def realign(self, force=False):
        """If the board has been nudged, find it again from its squares and
        move the grid onto it, keeping which corner is a1. Returns True if
        the grid moved. Only the cheap alignment check runs normally; the
        slower board finder only when that check says the grid is off, or
        with force=True (the pieces all changed at once, which a slide too
        small for the check to see can do)."""
        if self.alignment is None or self.find_board is None or self.corners is None:
            return False
        frame = self.frame()
        now = self.alignment(frame, self.corners)
        if self.baseline is None:
            self.baseline = now
        if not force and (self.baseline < 0.5 or now >= 0.85 * self.baseline):
            return False                # still lined up (or the check can't tell)
        found = self.find_board(frame, self.corners)
        if not found:
            return False
        c, f = np.float32(self.corners), np.float32(found)
        side = float(np.linalg.norm(c[0] - c[1])) / 8
        fixed = self.alignment(frame, found)
        shift = float(np.abs(f - c).max())
        if shift > 2 * side or fixed < now or (fixed == now and shift < 0.02 * side):
            return False                # not a small nudge, or no better: leave it
        self.corners = [(round(float(x), 2), round(float(y), 2)) for x, y in found]
        self.H = homography_from_corners(self.corners)
        self.baseline = fixed
        self.on_realign(self.corners)
        return True

    def wait_for_board_change(self, reference, change_threshold, check=lambda: None, **kw):
        """Wait until the board has settled into a state that differs from
        `reference` on at least one square (beyond any whole-board lighting change).
        If the board itself was nudged, the grid is moved back onto it first."""
        while True:
            settled = self.wait_until_still(check, **kw)
            if self.realign():
                settled = self.board()
            scores = change_scores(reference, settled)
            if max(scores) - float(np.median(scores)) > change_threshold:
                return settled
