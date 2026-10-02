"""Offline test of lessons on the real board: a fake camera shows rendered
images of a board this test sets up and moves pieces on, and the game loop
checks the lesson moves (no Stockfish needed).

  python3 test_lesson_board.py
"""
import threading

import chess

from game import Game
from lessons import Runner
from test_detector import CORNERS, render
from test_game import FakeCamera, wait_for
from vision import BoardCamera, homography_from_corners


def set_position(physical, board):
    with physical.lock:
        physical.board = board.copy(stack=False)
        physical.nudged = {}
        physical.image = render(physical.board)


def main():
    physical = FakeCamera()
    cam = BoardCamera(physical, homography_from_corners(CORNERS))
    said = []
    game = Game(cam, lambda *a, **k: None, say=lambda t: said.append(t), on_update=lambda s: None)
    threading.Thread(target=game.run, daemon=True).start()
    tutor = Runner()
    results = []

    def moved(move):                           # what main.py does
        ok, message = tutor.try_move(move)
        said.append(message)
        if ok and tutor.wants_move:
            game.request_lesson(tutor.board, moved)
        return ok

    def check(name, ok):
        print(f"{'ok  ' if ok else 'FAIL'} {name}")
        results.append(ok)

    # Knight lesson, step 1: any knight move; the position is already set up.
    tutor.open("knight")
    set_position(physical, tutor.board)
    game.request_lesson(tutor.board, moved)
    wait_for(lambda: game.status == "Lesson: make the move on the board.")
    physical.play(chess.Move.from_uci("d4f5"))
    wait_for(lambda: tutor.i == 1)
    check("knight move read from the board and accepted", any(t.startswith("Correct") for t in said))

    # Step 2 needs a new position: the camera asks for it to be set up.
    wait_for(lambda: any(t.startswith("Put a white") for t in said))
    print("   asked:", [t for t in said if t.startswith("Put a")][-1])
    set_position(physical, tutor.board)
    wait_for(lambda: game.status == "Lesson: make the move on the board.")
    check("set-up check passes once the position is right", True)

    # A wrong move, put back, then the right one.
    physical.play(chess.Move.from_uci("b1a3"))
    wait_for(lambda: any("Put the piece back" in t for t in said))
    check("wrong move refused", tutor.i == 1 and any(t.startswith("Not quite") for t in said))
    set_position(physical, tutor.board)
    wait_for(lambda: game.status == "Lesson: make the move on the board.")
    physical.play(chess.Move.from_uci("b1c3"))
    wait_for(lambda: tutor.i == 2)
    check("right move accepted after putting the piece back", True)

    # "It's set up" skips the camera check.
    wait_for(lambda: game.status == "Lesson: set up the position shown on the page.")
    game.request_set_up()
    wait_for(lambda: game.status == "Lesson: make the move on the board.")
    check("It's set up skips the position check", True)

    # An opening, both sides, on the board.
    tutor.open("italian")
    tutor.next()
    set_position(physical, tutor.board)
    game.request_lesson(tutor.board, moved)
    for san in ["e4", "e5", "Nf3"]:
        wait_for(lambda: game.status == "Lesson: make the move on the board."
                 and game.board.board_fen() == tutor.board.board_fen())
        n = tutor.i
        physical.play(physical.board.parse_san(san))
        wait_for(lambda: tutor.i > n)
    check("opening moves for both sides read in turn", tutor.i == 4)

    game.request_idle()
    wait_for(lambda: game.settings is None)
    check("idle stops watching", True)
    print(f"{sum(results)}/{len(results)} passed")
    raise SystemExit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
