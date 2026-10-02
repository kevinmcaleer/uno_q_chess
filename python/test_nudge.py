"""Checks a move is still read when the player knocks a neighbouring piece
off-centre while making it (the knocked piece stays where it lands).

  python3 test_nudge.py
"""
import chess
import numpy as np

from detector import infer_move, squares_touched
from test_detector import CORNERS, game_moves, render
from vision import change_scores, homography_from_corners, occupancy_mismatches, warp

H = homography_from_corners(CORNERS)


def seen(board, img):
    extra, missing = occupancy_mismatches(img, {s: p.color for s, p in board.piece_map().items()})
    return set(extra), set(missing)


def main(shift=28):
    rng = np.random.default_rng(5)
    read = wrong = unread = 0
    for seed in range(4):
        board, nudged = chess.Board(), {}
        ref = warp(render(board), H)
        for uci in game_moves(seed, 100):
            move = chess.Move.from_uci(uci)
            touched = squares_touched(board, move)
            after_board = board.copy()
            after_board.push(move)
            for s in touched:
                nudged.pop(s, None)                     # pieces that moved are centred
            # knock a piece next to the from or to square
            near = [s for s in after_board.piece_map() if s not in touched and
                    min(chess.square_distance(s, t) for t in touched) == 1]
            if near:
                s = near[rng.integers(len(near))]
                angle = rng.uniform(0, 2 * np.pi)
                nudged[s] = (int(shift * np.cos(angle)), int(shift * np.sin(angle)))
            after = warp(render(after_board, nudged), H)
            got, _ = infer_move(board, change_scores(ref, after), occupancy=seen(board, after))
            if got == move:
                read += 1
            elif got is None:
                unread += 1
            else:
                wrong += 1
                print(f"seed {seed}: {uci} read as {got.uci()}")
            board.push(move)                            # the game carries on as played
            ref = after
    print(f"{read} read, {unread} unreadable, {wrong} wrong (pieces knocked {shift} px of a {100} px square)")
    assert wrong == 0 and unread == 0


if __name__ == "__main__":
    main()
