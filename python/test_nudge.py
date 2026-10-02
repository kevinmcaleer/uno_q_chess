"""Checks a move is still read when the player knocks a neighbouring piece
off-centre while making it (the knocked piece stays where it lands).

  python3 test_nudge.py
"""
import chess
import numpy as np

from detector import infer_move, knocked_pieces, squares_touched
from test_detector import CORNERS, game_moves, render
from vision import change_scores, homography_from_corners, occupancy_mismatches, warp

H = homography_from_corners(CORNERS)


def seen(board, img):
    extra, missing = occupancy_mismatches(img, {s: p.color for s, p in board.piece_map().items()})
    return set(extra), set(missing)


def main(shift=28):
    rng = np.random.default_rng(5)
    read = wrong = unread = named = 0
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
                knocked = knocked_pieces(board, move, change_scores(ref, after),
                                         seen(board, after)[1], 25)
                assert knocked is not None and len(knocked) <= 1, knocked
                named += bool(knocked)
            elif got is None:
                unread += 1
            else:
                wrong += 1
                print(f"seed {seed}: {uci} read as {got.uci()}")
            board.push(move)                            # the game carries on as played
            ref = after
    print(f"{read} read, {unread} unreadable, {wrong} wrong (pieces knocked {shift} px of a {100} px square); "
          f"knocked piece named {named} times, never more than one")
    assert wrong == 0 and unread == 0


def board_slides():
    """The whole board slides a few pixels (too little to re-align) while a
    move is made: the move is read and no piece is said to be knocked."""
    rng = np.random.default_rng(9)
    quiet = 0
    board = chess.Board()
    ref = warp(render(board), H)
    for i, uci in enumerate(game_moves(1, 40)):
        move = chess.Move.from_uci(uci)
        after_board = board.copy()
        after_board.push(move)
        dx, dy = rng.uniform(2, 4) * rng.choice([-1, 1]), rng.uniform(-2, 2)
        corners = [(x + dx, y + dy) for x, y in CORNERS]
        after = warp(render(after_board, corners=corners), H)
        scores = change_scores(ref, after)
        got, _ = infer_move(board, scores, occupancy=seen(board, after))
        assert got == move, f"{uci} read as {got}"
        knocked = knocked_pieces(board, move, scores, seen(board, after)[1], 25)
        assert not knocked, f"{uci}: {len(knocked)} pieces said to be knocked"
        quiet += 1
        board.push(move)
        ref = warp(render(board), H)                    # board put back for the next move
    print(f"Board slid 2-4 px during {quiet} moves: all read, no knocked pieces named")


if __name__ == "__main__":
    main()
    board_slides()
