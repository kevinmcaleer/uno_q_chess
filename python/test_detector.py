"""Offline test: renders fake camera images of a board (seen at an angle,
with noise) and checks the move detector reads a whole game correctly,
including captures, castling, en passant and promotion.

  python3 test_detector.py
"""
import chess
import cv2
import numpy as np

from detector import infer_move
from vision import SQ, WARP_SIZE, change_scores, homography_from_corners, warp

CORNERS = [(380, 90), (930, 110), (1010, 650), (300, 630)]   # a8 h8 h1 a1 in the fake image
rng = np.random.default_rng(1)


HEIGHT = {chess.PAWN: 0.55, chess.KNIGHT: 0.7, chess.BISHOP: 0.8, chess.ROOK: 0.6,
          chess.QUEEN: 0.9, chess.KING: 1.0}


def render(board, nudged=None, corners=CORNERS, lean=0.0, side_light=0.0):
    """nudged: {square: (dx, dy)} pixels a piece sits off-centre.
    lean: 0 for flat discs seen from above. Above 0, real 3D pieces seen
    from the side: each piece rises towards the top of the picture by up to
    `lean` squares (a king; shorter pieces less), covering part of the square
    behind it, and the colours are a wooden set on a black and cream board
    (like Kev's). side_light: the picture is that much brighter on the left
    than the right (0.4 = +20% on the left edge, -20% on the right), with glare
    on the left half that lifts the black squares to grey."""
    nudged = nudged or {}
    top = np.zeros((WARP_SIZE, WARP_SIZE, 3), np.uint8)
    light, dark = ((181, 217, 240), (99, 136, 181)) if not lean else ((150, 210, 235), (45, 38, 36))
    for sq in chess.SQUARES:
        f, r = chess.square_file(sq), chess.square_rank(sq)
        x, y = f * SQ, (7 - r) * SQ
        top[y:y + SQ, x:x + SQ] = light if (f + r) % 2 else dark
    # back rows first, so nearer pieces cover the tops of the ones behind
    for sq in sorted(board.piece_map(), key=lambda s: -chess.square_rank(s)):
        p = board.piece_at(sq)
        f, r = chess.square_file(sq), chess.square_rank(sq)
        x, y = f * SQ, (7 - r) * SQ
        dx, dy = nudged.get(sq, (0, 0))
        c = (x + SQ // 2 + dx, y + SQ // 2 + dy)
        if not lean:
            body = (235, 235, 235) if p.color else (40, 40, 40)
            cv2.circle(top, c, 34, body, -1)
            cv2.putText(top, p.symbol().upper(), (c[0] - 12, c[1] + 12),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 0, 200), 3)
            continue
        body = (195, 225, 240) if p.color else (40, 60, 90)       # boxwood / dark stained
        rise = int(lean * HEIGHT[p.piece_type] * SQ)
        head = (c[0], c[1] - rise)
        cv2.circle(top, c, 32, body, -1)                           # base
        cv2.rectangle(top, (c[0] - 16, head[1]), (c[0] + 16, c[1]), body, -1)
        cv2.circle(top, head, 22, body, -1)                        # head
        edge = tuple(int(v * 0.7) for v in body)
        cv2.circle(top, head, 22, edge, 2)
    # project onto a skewed "camera" frame and add sensor noise
    H = homography_from_corners(corners)
    cam = cv2.warpPerspective(top, np.linalg.inv(H), (1280, 720)).astype(np.float32)
    if side_light:
        # brighter towards the left, plus glare off the left of the board
        # (which lifts the black squares to grey)
        x = np.linspace(0, 1, cam.shape[1])[None, :, None]
        cam = cam * (1 + side_light * (0.5 - x)) + 120 * side_light * np.clip(1 - 2 * x, 0, 1)
    noise = rng.normal(0, 4, cam.shape)
    return np.clip(cam + noise, 0, 255).astype(np.uint8)


# Opening with castling both sides and en passant, then random legal play
# (which reliably produces captures and promotions).
OPENING = "e2e4 g8f6 e4e5 d7d5 e5d6 e7d6 g1f3 f8e7 f1e2 e8g8 e1g1".split()


def game_moves(seed, plies=150):
    r = np.random.default_rng(seed)
    b = chess.Board()
    for uci in OPENING:
        b.push_uci(uci)
    while len(b.move_stack) < plies and not b.is_game_over():
        moves = list(b.legal_moves)
        b.push(moves[r.integers(len(moves))])
    return [m.uci() for m in b.move_stack]


def main():
    counts = {}
    total = 0
    for seed in range(4):
        total += play_game(game_moves(seed), counts)
    total += play_game(["a7a8q", "h7h6", "a8b8"], counts, chess.Board("8/P6k/8/8/8/8/8/K7 w - - 0 1"))
    total += play_game(["b2a1q"], counts, chess.Board("7k/8/8/8/8/8/1p6/R5K1 b - - 0 1"))
    print(f"\nAll {total} moves read correctly: {counts}")


def play_game(game, counts, board=None):
    H = homography_from_corners(CORNERS)
    board = board or chess.Board()
    ref = warp(render(board), H)
    for uci in game:
        true_move = chess.Move.from_uci(uci)
        after = warp(render(_after(board, true_move)), H)
        move, fit = infer_move(board, change_scores(ref, after))
        tag = ("castle" if board.is_castling(true_move) else
               "en passant" if board.is_en_passant(true_move) else
               "promotion" if true_move.promotion else
               "capture" if board.is_capture(true_move) else "")
        assert move == true_move, f"expected {uci}, read {move} (fit {fit:.1f})"
        counts[tag or "quiet"] = counts.get(tag or "quiet", 0) + 1
        board.push(move)
        ref = after
    # a board where nothing changed must not produce a move
    move, _ = infer_move(board, change_scores(ref, warp(render(board), H)))
    assert move is None
    return len(game)


def _after(board, move):
    b = board.copy()
    b.push(move)
    return b


if __name__ == "__main__":
    main()
