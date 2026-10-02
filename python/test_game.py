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
        self.image = render(self.board)
        self.lock = threading.Lock()

    def capture(self):
        time.sleep(0.02)
        with self.lock:
            return self.image

    def play(self, move):
        with self.lock:
            self.board.push(move)
            self.image = render(self.board)


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
    game.request_new_game(colour="white", skill=3, think=0.1)
    typed = False

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
            physical.play(move)
        else:
            wait_for(lambda: game.expected is not None)
            physical.play(game.expected)
        wait_for(lambda: len(game.board.move_stack) > n)
        assert game.board.move_stack == physical.board.move_stack, (game.board, physical.board)
        print(f"{n + 1:2d}. {game.board.peek().uci()}", flush=True)

    # a new game request interrupts the current one
    game.request_new_game(colour="black", skill=1, think=0.1)
    wait_for(lambda: game.settings and game.settings["colour"] == "black")
    print(f"\nAll {plies} plies read correctly, new game started. "
          f"Said {len(said)} things, e.g. {said[-3:]}")


if __name__ == "__main__":
    main()
