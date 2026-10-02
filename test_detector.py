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


def render(board):
    top = np.zeros((WARP_SIZE, WARP_SIZE, 3), np.uint8)
    for sq in chess.SQUARES:
        f, r = chess.square_file(sq), chess.square_rank(sq)
        x, y = f * SQ, (7 - r) * SQ
        top[y:y + SQ, x:x + SQ] = (181, 217, 240) if (f + r) % 2 else (99, 136, 181)
        p = board.piece_at(sq)
        if p:
            c = (x + SQ // 2, y + SQ // 2)
            body = (235, 235, 235) if p.color else (40, 40, 40)
            cv2.circle(top, c, 34, body, -1)
            cv2.putText(top, p.symbol().upper(), (c[0] - 12, c[1] + 12),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 0, 200), 3)
    # project onto a skewed "camera" frame and add sensor noise
    H = homography_from_corners(CORNERS)
    cam = cv2.warpPerspective(top, np.linalg.inv(H), (1280, 720))
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
