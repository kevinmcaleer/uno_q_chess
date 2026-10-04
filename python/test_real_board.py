"""A real set like Kev's (test_detector.render with lean): wooden pieces
on a black and cream board, white pieces close in colour to the cream
squares and dark ones to the black, seen from a little off overhead (each
piece's top leans over the square behind) and lit more from one side. Checks moves are still read
and the "?" marks don't flag squares wrongly.

  python3 test_real_board.py
"""
import chess

from detector import infer_move
from test_detector import CORNERS, game_moves, render
from vision import change_scores, homography_from_corners, occupancy_mismatches, warp

H = homography_from_corners(CORNERS)


def run(lean, side_light, games=4, plies=80, marks=8.0):
    read = unread = wrong = flagged = checked = 0
    for seed in range(games):
        board = chess.Board()
        ref = warp(render(board, lean=lean, side_light=side_light), H)
        for uci in game_moves(seed, plies):
            move = chess.Move.from_uci(uci)
            after_board = board.copy()
            after_board.push(move)
            after = warp(render(after_board, lean=lean, side_light=side_light), H)
            pieces = {s: p.color for s, p in board.piece_map().items()}
            got, _ = infer_move(board, change_scores(ref, after), occupancy=occupancy_mismatches(after, pieces))
            if got == move:
                read += 1
            elif got is None:
                unread += 1
            else:
                wrong += 1
            board.push(move)
            ref = after
            # a still board that matches the game: no square should be marked
            extra, missing = occupancy_mismatches(after, {s: p.color for s, p in board.piece_map().items()},
                                                  marks)
            checked += 1
            flagged += bool(extra or missing)
    return read, unread, wrong, flagged, checked


def main():
    flagged_tall = None
    for lean, side in ((0.0, 0.0), (0.3, 0.0), (0.3, 0.4), (0.6, 0.4)):
        read, unread, wrong, flagged, checked = run(lean, side)
        print(f"pieces rising {lean:.1f} squares, light {side:.0%} brighter on one side: {read} read, "
              f"{unread} unreadable, {wrong} wrong; '?' shown on {flagged} of {checked} correct boards")
        assert wrong == 0 and unread <= 0.01 * checked
        if lean <= 0.3:
            assert flagged == 0
        flagged_tall = flagged
    # very tall pieces lean right over the square behind and get marked; the
    # "?" marks slider cuts that down (test_occupancy still passes at 30)
    *_, flagged, checked = run(0.6, 0.4, marks=30)
    print(f"  with the \"?\" marks slider at 30: '?' shown on {flagged} of {checked}")
    assert flagged <= 0.6 * flagged_tall


if __name__ == "__main__":
    main()
