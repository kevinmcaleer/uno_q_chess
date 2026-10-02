"""Offline test of the whole game loop: a fake camera shows rendered images of
a "real" board that this test moves pieces on, and a real Stockfish plays.
The human's moves are random legal moves; one is typed instead of played.

  python3 test_game.py          # needs Stockfish installed (apt install stockfish)

Set STOCKFISH_HOST/STOCKFISH_PORT to test against the Stockfish brick over TCP.
"""
import threading
import time

import chess
import numpy as np

from engine import Engine
from game import Game
from test_detector import CORNERS, render
from vision import BoardCamera, homography_from_corners


class FakeCamera:
    """Renders each position once (test_still.py covers per-frame noise and flicker)."""

    def __init__(self):
        self.board = chess.Board()
        self.nudged = {}
        self.image = render(self.board)
        self.lock = threading.Lock()

    def capture(self):
        time.sleep(0.02)
        with self.lock:
            return self.image

    def play(self, move, knock=None):
        """knock: a square whose piece gets knocked off-centre at the same time."""
        with self.lock:
            self.board.push(move)
            self.nudged.pop(move.to_square, None)
            if knock is not None:
                self.nudged[knock] = (26, -14)
            self.image = render(self.board, self.nudged)


def wait_for(cond, timeout=30):
    end = time.monotonic() + timeout
    while not cond():
        if time.monotonic() > end:
            raise TimeoutError
        time.sleep(0.05)


def main(plies=12):
    rng = np.random.default_rng(3)
    physical = FakeCamera()
    cam = BoardCamera(physical, homography_from_corners(CORNERS))
    said = []
    game = Game(cam, lambda skill, think, on_wait=None: Engine(skill, think, on_wait=on_wait),
                say=lambda t: said.append(t), on_update=lambda s: None)
    threading.Thread(target=game.run, daemon=True).start()
    game.request_new_game(colour="white", skill=3, think=0.1, coach=True)
    typed = False
    knocked = None

    wait_for(lambda: game.status == "Your move.")
    while len(game.board.move_stack) < plies:
        n = len(game.board.move_stack)
        if game.board.turn == chess.WHITE:
            moves = list(game.board.legal_moves)
            move = moves[rng.integers(len(moves))]
            if move.promotion and move.promotion != chess.QUEEN:
                continue
            if not typed and n >= 4:
                game.request_typed_move(move.uci())      # typed, then made on the board
                typed = True
            # once, knock a neighbouring piece while moving
            near = [sq for sq in game.board.piece_map() if sq not in (move.from_square, move.to_square)
                    and chess.square_distance(sq, move.from_square) == 1]
            knock = near[0] if n == 2 and near else None
            physical.play(move, knock)
            if knock is not None:
                knocked = chess.square_name(knock)
        else:
            wait_for(lambda: game.expected is not None)
            physical.play(game.expected)
        wait_for(lambda: len(game.board.move_stack) > n)
        assert game.board.move_stack == physical.board.move_stack, (game.board, physical.board)
        print(f"{n + 1:2d}. {game.board.peek().uci()}", flush=True)

    assert knocked and any("looks knocked" in t and knocked in t for t in said), said
    print(f"Knocked the piece on {knocked}: read the move anyway and asked to centre it")

    openers = ("great move", "good move", "not quite", "that's a mistake", "oh no", "nice")
    coached = [t for t in said if t.lower().startswith(openers)]
    assert coached, said
    print("Coach said:", *coached, sep="\n  ")

    # a new game request interrupts the current one
    game.request_new_game(colour="black", skill=1, think=0.1)
    wait_for(lambda: game.settings and game.settings["colour"] == "black")
    print(f"\nAll {plies} plies read correctly, new game started. "
          f"Said {len(said)} things, e.g. {said[-3:]}")


if __name__ == "__main__":
    main()
