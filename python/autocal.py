"""Find the board in a camera frame from its chequerboard pattern.

OpenCV's chessboard detector finds the inner corners where four squares
meet: all 7x7 on an empty board, or fewer rows when pieces hide some.
Fitting a homography to every corner it finds gives the four outer board
corners far more precisely than clicking.

With rough corners from the user, the board is straightened first, which
also makes a small, far-away board much easier to detect, and the user's
orientation is kept. Without them the whole frame is searched and the
orientation is worked out from the square colours (a1 is dark) and, when
the pieces are set up, which side White is on.
"""
import cv2
import numpy as np

from vision import SQ, WARP_SIZE, homography_from_corners

PAD = SQ                                      # border kept around the straightened board
FLAGS = cv2.CALIB_CB_EXHAUSTIVE | cv2.CALIB_CB_ACCURACY | cv2.CALIB_CB_NORMALIZE_IMAGE
SIZES = [(7, 7), (7, 6), (7, 5), (7, 4), (7, 3)]   # biggest pattern first
BOX = np.array([[[0, 0]], [[WARP_SIZE, 0]], [[WARP_SIZE, WARP_SIZE]], [[0, WARP_SIZE]]],
               dtype=np.float32)


def _gray(img):
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img


def _detect(gray):
    """Return (points Nx2 in OpenCV's row-major order, (cols, rows)) or None."""
    for size in SIZES:
        for scale in (1, 2):
            img = gray if scale == 1 else cv2.resize(gray, None, fx=scale, fy=scale,
                                                     interpolation=cv2.INTER_CUBIC)
            found, pts = cv2.findChessboardCornersSB(img, size, FLAGS)
            if found:
                return pts.reshape(-1, 2) / scale, size
    return None


def _outer(grid, image_pts):
    """Fit board-warp coordinates -> image and return the four outer corners
    (top-left, top-right, bottom-right, bottom-left of the warp)."""
    H, _ = cv2.findHomography(np.float32(grid), np.float32(image_pts), 0)
    return cv2.perspectiveTransform(BOX, H).reshape(4, 2)


def _square_stats(frame, corners):
    """Mean and spread of brightness per square (python-chess order)."""
    top = cv2.warpPerspective(_gray(frame), homography_from_corners(corners),
                              (WARP_SIZE, WARP_SIZE)).astype(np.float32)
    m = SQ // 5
    mean, std = np.zeros(64), np.zeros(64)
    for sq in range(64):
        x, y = (sq % 8) * SQ, (7 - sq // 8) * SQ
        patch = top[y + m:y + SQ - m, x + m:x + SQ - m]
        mean[sq], std[sq] = patch.mean(), patch.std()
    return mean, std


def _score(frame, corners):
    """(parity, setup, white_side) for a labelling a8, h8, h1, a1.
    parity > 0 when light squares are brighter than dark ones (a1 dark),
    measured on ranks 3-6, which are empty on an empty board and at the start.
    setup: how much busier ranks 1-2 and 7-8 are than the middle (pieces).
    white_side: ranks 1-2 brighter than ranks 7-8."""
    mean, std = _square_stats(frame, corners)
    mid = range(16, 48)
    dark = np.mean([mean[s] for s in mid if (s % 8 + s // 8) % 2 == 0])
    light = np.mean([mean[s] for s in mid if (s % 8 + s // 8) % 2 == 1])
    outer = np.r_[std[0:16], std[48:64]].mean()
    return light - dark, outer - std[16:48].mean(), mean[0:16].mean() - mean[48:64].mean()


def _clockwise(c):
    """a8 -> h8 -> h1 -> a1 goes clockwise on screen (y down) for a board seen
    from above; a mirrored labelling goes the other way."""
    return sum(c[i][0] * c[(i + 1) % 4][1] - c[(i + 1) % 4][0] * c[i][1] for i in range(4)) > 0


def _refine(frame, approx):
    """Detect within the board straightened by the user's rough corners."""
    dst = np.float32([[PAD, PAD], [PAD + WARP_SIZE, PAD],
                      [PAD + WARP_SIZE, PAD + WARP_SIZE], [PAD, PAD + WARP_SIZE]])
    Hw = cv2.getPerspectiveTransform(np.float32(approx), dst)
    top = cv2.warpPerspective(_gray(frame), Hw, (WARP_SIZE + 2 * PAD,) * 2)
    hit = _detect(top)
    if hit is None:
        return None
    pts, _ = hit
    # The straightened board is nearly square to the axes, so each corner's
    # place in the grid is its position rounded to whole squares (as long as
    # the clicks were within half a square).
    grid = np.round((pts - PAD) / SQ)
    if grid.min() < 1 or grid.max() > 7 or len({tuple(g) for g in grid}) != len(grid):
        return None
    image_pts = cv2.perspectiveTransform(pts.reshape(-1, 1, 2).astype(np.float32),
                                         np.linalg.inv(Hw)).reshape(-1, 2)
    return _outer(grid * SQ, image_pts)


# Sample points around each of the 49 inner corners, a little way into each
# of the four squares that meet there: near a corner, clear of a centred piece.
_IJ = np.array([(i, j) for j in range(1, 8) for i in range(1, 8)], dtype=np.float32)
_D = 0.15
_OFFS = np.float32([[-_D, -_D], [_D, _D], [_D, -_D], [-_D, _D]])      # TL, BR, TR, BL
# Expected sign of (TL + BR) - (TR + BL): negative where the top-left square is
# dark. In board-warp squares, the square left of / above corner (i, j) is
# file i-1, rank 8-j (0-based), dark when their sum is even.
_SIGN = np.where(((_IJ[:, 0] - 1) + (8 - _IJ[:, 1])) % 2 == 0, -1.0, 1.0)


def _responses(gray, corners, d=_D):
    """Signed light/dark contrast at each of the 49 inner corners (positive
    where it matches a chequerboard with a1 dark), sampling d squares away."""
    H = cv2.getPerspectiveTransform(np.float32([[0, 0], [8, 0], [8, 8], [0, 8]]),
                                    np.float32(corners))
    offs = _OFFS * (d / _D)
    pts = (_IJ[:, None, :] + offs[None, :, :]).reshape(-1, 1, 2)
    xy = cv2.perspectiveTransform(pts, H).reshape(1, -1, 2)
    v = cv2.remap(gray, xy[..., 0], xy[..., 1], cv2.INTER_LINEAR,
                  borderMode=cv2.BORDER_REPLICATE).astype(np.float32).reshape(-1, 4)
    return _SIGN * ((v[:, 0] + v[:, 1]) - (v[:, 2] + v[:, 3]))


def _checker_score(gray, corners):
    """How well a labelling's grid lands on the real chequerboard: mean signed
    contrast at the 49 inner corners. Strongly positive only when the grid is
    in the right place and a1 is dark."""
    return float(np.mean(_responses(gray, corners)))


def _consistent(gray, corners):
    """True if (nearly) every inner corner shows the expected light/dark
    pattern, i.e. this really is the board and not a lucky partial match."""
    r = _responses(gray, corners)
    return np.mean(r > 0) > 0.8 and r.mean() > 0.4 * np.abs(r).mean()


def _optimize(gray, c):
    """Nudge the four corners to line the grid up with the squares, by
    climbing the chequerboard score. Works with pieces on the board (it only
    looks near the square corners) and from clicks up to ~1/3 square out.
    A coarse pass samples well into the squares to find the right place, a
    fine pass samples right next to the corners to pin it down."""
    c = np.float32(c).copy()
    side = float(np.linalg.norm(c[0] - c[1])) / 8
    passes = [((0.12, 0.22, 0.32), side / 12, side / 3, side / 16),
              ((0.04, 0.07, 0.10), side / 40, side / 16, 0.05)]
    for ds, sigma, step, stop in passes:
        blur = cv2.GaussianBlur(gray, (0, 0), max(0.5, sigma)).astype(np.float32)

        def score(cc):
            return sum(float(np.mean(_responses(blur, cc, d))) for d in ds)

        best = score(c)
        while step > stop:
            improved = False
            for k in range(4):
                for axis in range(2):
                    for sgn in (1, -1):
                        trial = c.copy()
                        trial[k, axis] += sgn * step
                        sc = score(trial)
                        if sc > best:
                            best, c, improved = sc, trial, True
            if not improved:
                step /= 2
    return c


def _search(frame):
    """Detect in the whole frame and work out where the pattern sits and the
    orientation."""
    gray = _gray(frame)
    hit = _detect(gray)
    if hit is None:
        return None
    pts, (cols, rows) = hit
    k = np.arange(len(pts))
    c_idx, r_idx = k % cols, k // cols
    candidates = []
    # A partial pattern (pieces hiding some corners) could sit anywhere on the
    # board and either way round, so try every placement.
    for transpose in (False, True):
        gi, gj = (r_idx, c_idx) if transpose else (c_idx, r_idx)
        w, h = (rows, cols) if transpose else (cols, rows)
        for ox in range(1, 8 - w + 1):
            for oy in range(1, 8 - h + 1):
                grid = np.stack([(gi + ox) * SQ, (gj + oy) * SQ], axis=1)
                c = _outer(grid, pts)
                if not _clockwise(c):
                    c = c[[1, 0, 3, 2]]
                for rot in range(4):
                    r = np.roll(c, -rot, axis=0)
                    candidates.append((_checker_score(gray, r), r))
    best = max(s for s, _ in candidates)
    if best <= 0:
        return None
    # A half turn fits the squares equally well. If the pieces are set up,
    # White's (brighter) pieces go on ranks 1-2; on an empty board, assume
    # White sits at the bottom of the picture.
    close = [r for s, r in candidates if s > 0.9 * best]
    scored = [(_score(frame, r), r) for r in close]
    if max(sc[1] for sc, _ in scored) > 4:
        return max(scored, key=lambda c: c[0][2])[1]
    return max(close, key=lambda r: r[2][1] + r[3][1])


def find_board(frame, approx=None):
    """Return the outer corners [a8, h8, h1, a1] as float pixel positions, or
    None if the chequerboard can't be found. approx: rough corners, same order
    (their orientation is kept)."""
    gray = _gray(frame)
    starts = [np.float32(approx)] if approx is not None else []
    if not starts or not _consistent(gray, _optimize(gray, starts[0])):
        found = _search(frame)
        if found is not None:
            if approx is not None:
                # keep the user's orientation: the rotation closest to their corners
                found = min((np.roll(found, -k, axis=0) for k in range(4)),
                            key=lambda r: np.abs(r - starts[0]).sum())
            starts.append(np.float32(found))
    # Climbing the score lines the grid up even with pieces in the way. The
    # detector, run on the board straightened by that, is more precise when it
    # agrees; if it doesn't (pieces can fool it on a small board), trust the climb.
    best = None
    for start in starts:
        climbed = _optimize(gray, start)
        if not _consistent(gray, climbed):
            continue
        side = float(np.linalg.norm(climbed[0] - climbed[1])) / 8
        refined = _refine(frame, climbed)
        if refined is not None and np.abs(np.float32(refined) - climbed).max() < 0.15 * side \
                and _consistent(gray, refined):
            climbed = np.float32(refined)
        if best is None or _checker_score(gray, climbed) > _checker_score(gray, best):
            best = climbed
    return None if best is None else [(float(x), float(y)) for x, y in best]
