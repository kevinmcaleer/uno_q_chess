"""Checks the camera-vs-tracked-position check: no false alarms through whole
games, and a piece missing from, or added to, the board is spotted, under
dimmer and brighter lighting too.

  python3 test_occupancy.py
"""
import chess
import numpy as np

from test_detector import CORNERS, game_moves, render
from vision import homography_from_corners, occupancy_mismatches, warp

H = homography_from_corners(CORNERS)


def look(board, gain):
    img = render(board).astype(np.float32) * gain
    return warp(np.clip(img, 0, 255).astype(np.uint8), H)


def main():
    checked = problems = 0
    for seed in range(3):
        board = chess.Board()
        for i, uci in enumerate(game_moves(seed, 120)):
            if i % 10 == 0:
                gain = (0.75, 1.0, 1.15)[(i // 10) % 3]
                tracked = {sq: p.color for sq, p in board.piece_map().items()}
                cases = [("as tracked", board, [], [])]
                gone = list(tracked)[i % len(tracked)]
                b = board.copy()
                b.remove_piece_at(gone)
                cases.append((f"{chess.square_name(gone)} removed", b, [], [gone]))
                empty = [sq for sq in chess.SQUARES if sq not in tracked]
                new = empty[i % len(empty)]
                b = board.copy()
                b.set_piece_at(new, chess.Piece(chess.PAWN, i % 20 < 10))
                cases.append((f"piece added on {chess.square_name(new)}", b, [new], []))
                for name, physical, want_extra, want_missing in cases:
                    checked += 1
                    got = occupancy_mismatches(look(physical, gain), tracked)
                    if got != (want_extra, want_missing):
                        problems += 1
                        print(f"seed {seed} ply {i} light x{gain}, {name}: got {got}")
            board.push_uci(uci)
    print(f"{checked - problems} of {checked} boards checked correctly")
    assert problems == 0


if __name__ == "__main__":
    main()
