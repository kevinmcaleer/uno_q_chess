"""Thin wrapper around the Stockfish chess engine (via python-chess)."""
import shutil

import chess
import chess.engine


class Engine:
    def __init__(self, path=None, skill=5, think_time=0.5):
        path = path or shutil.which("stockfish") or "/usr/games/stockfish"
        self.engine = chess.engine.SimpleEngine.popen_uci(path)
        # Skill Level 0 (beginner) .. 20 (full strength)
        self.engine.configure({"Skill Level": skill})
        self.limit = chess.engine.Limit(time=think_time)

    def play(self, board):
        return self.engine.play(board, self.limit).move

    def suggest(self, board):
        """Engine's preferred move for the side to move, used for hints."""
        info = self.engine.analyse(board, self.limit)
        pv = info.get("pv")
        return pv[0] if pv else None

    def close(self):
        self.engine.quit()
