"""Checks the grid follows the board when the board itself gets nudged
mid-game: on its own, together with a move, and turned slightly, keeping
which corner is a1.

  python3 test_realign.py
"""
import threading
import time

import chess
import numpy as np

from autocal import alignment, find_board
from detector import infer_move
from test_detector import CORNERS, render
from vision import BoardCamera, change_scores, occupancy_mismatches


class Timeout(Exception):
    pass


class Table:
    """A camera looking at a board that can be moved on the table."""

    def __init__(self):
        self.board = chess.Board()
        self.corners = [list(map(float, c)) for c in CORNERS]
        self.lock = threading.Lock()
        self._draw()

    def _draw(self):
        self.image = render(self.board, corners=self.corners)

    def capture(self):
        time.sleep(0.03)
        with self.lock:
            return self.image

    def nudge(self, dx, dy, degrees):
        c = np.float32(self.corners)
        centre, a = c.mean(0), np.radians(degrees)
        R = np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]], np.float32)
        with self.lock:
            self.corners = ((c - centre) @ R.T + centre + [dx, dy]).tolist()
            self._draw()

    def play(self, uci):
        with self.lock:
            self.board.push_uci(uci)
            self._draw()


def wait_change(cam, reference, seconds):
    end = time.monotonic() + seconds

    def check():
        if time.monotonic() > end:
            raise Timeout

    try:
        return cam.wait_for_board_change(reference, 25, check)
    except Timeout:
        return None


def main():
    table = Table()
    cam = BoardCamera(table, corners=None)
    cam.set_calibration([tuple(c) for c in CORNERS])
    cam.alignment, cam.find_board = alignment, find_board
    realigned = []
    cam.on_realign = realigned.append
    tracked = chess.Board()
    reference = cam.wait_until_still()
    assert not cam.realign(), "an aligned board must be left alone"

    def error():
        return float(np.abs(np.float32(cam.corners) - np.float32(table.corners)).max())

    steps = [("nudge", (10, -6, 0)), ("move", "e2e4"), ("move", "e7e5"),
             ("nudge", (-14, 8, 1.5)), ("nudge+move", ((6, 12, -1), "g1f3")), ("move", "b8c6"),
             ("nudge", (0, 0, 3)), ("move", "f1c4")]
    for kind, what in steps:
        before = len(realigned)
        if kind == "nudge":
            table.nudge(*what)
            settled = wait_change(cam, reference, 8)
            assert settled is None, "a nudge alone must not count as a move"
            assert len(realigned) > before, "the grid should have followed the board"
            print(f"board nudged {what}: grid moved, now within {error():.1f} px, no move read")
            reference = cam.board()
            continue
        if kind == "nudge+move":
            table.nudge(*what[0])
            what = what[1]
        table.play(what)
        settled = wait_change(cam, reference, 15)
        assert settled is not None, f"{what} not seen"
        pieces = {s: p.color for s, p in tracked.piece_map().items()}
        move, fit = infer_move(tracked, change_scores(reference, settled), 10,
                               occupancy_mismatches(settled, pieces))
        assert move == chess.Move.from_uci(what), f"expected {what}, read {move}"
        tracked.push(move)
        reference = settled
        print(f"{kind} {what}: read correctly" +
              (f", grid moved, within {error():.1f} px" if len(realigned) > before else ""))
    assert error() < 2, error()
    a8 = np.float32(cam.corners[0])
    assert np.linalg.norm(a8 - np.float32(table.corners[0])) < 2, "a1 orientation changed"
    print(f"All steps passed; the grid followed {len(realigned)} nudges and kept a8/a1 in place")


if __name__ == "__main__":
    main()
