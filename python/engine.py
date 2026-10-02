"""Talks UCI to the Stockfish chess engine.

Stockfish runs as a child process: the binary given as `path` (on the UNO Q,
the one stockfish_install.py downloaded), else one installed on this machine.
If STOCKFISH_HOST is set it connects to a Stockfish served over TCP instead
(e.g. `socat TCP-LISTEN:4000,fork EXEC:stockfish`), which test_game.py uses.
"""
import os
import shutil
import socket
import subprocess
import time

import chess

HOST = os.environ.get("STOCKFISH_HOST")
PORT = int(os.environ.get("STOCKFISH_PORT", "4000"))


def find_local():
    """A Stockfish installed on this machine, if any."""
    return shutil.which("stockfish") or (
        "/usr/games/stockfish" if os.path.exists("/usr/games/stockfish") else None)


class Engine:
    def __init__(self, skill=5, think_time=0.5, path=None, connect_timeout=60, on_wait=None):
        local = None if HOST else (path or find_local())
        if not HOST and not local:
            raise RuntimeError("Stockfish not found")
        if local:
            self.proc = subprocess.Popen([local], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         text=True, bufsize=1)
            self.out, self.inp = self.proc.stdin, self.proc.stdout
        else:
            self.proc = None
            self.sock = self._connect(connect_timeout, on_wait)
            f = self.sock.makefile("rw", newline="\n")
            self.out = self.inp = f
        self._send("uci")
        self._wait_for("uciok")
        # Skill Level 0 (beginner) .. 20 (full strength)
        self.skill = skill
        self._send(f"setoption name Skill Level value {skill}")
        self._send("isready")
        self._wait_for("readyok")
        self.movetime = int(think_time * 1000)

    @staticmethod
    def _connect(timeout, on_wait):
        """Keep trying for a while in case the server is still starting."""
        deadline = time.monotonic() + timeout
        warned = False
        while True:
            try:
                return socket.create_connection((HOST, PORT), timeout=30)
            except OSError:
                if time.monotonic() > deadline:
                    raise RuntimeError(f"Could not reach Stockfish at {HOST}:{PORT}")
                if on_wait and not warned:
                    on_wait()
                    warned = True
                time.sleep(2)

    def _send(self, line):
        self.out.write(line + "\n")
        self.out.flush()

    def _wait_for(self, prefix):
        while True:
            line = self.inp.readline()
            if not line:
                raise RuntimeError("Stockfish closed the connection")
            if line.startswith(prefix):
                return line.strip()

    def play(self, board):
        moves = " ".join(m.uci() for m in board.move_stack)
        self._send(f"position fen {board.root().fen()}" + (f" moves {moves}" if moves else ""))
        self._send(f"go movetime {self.movetime}")
        best = self._wait_for("bestmove").split()[1]
        return None if best == "(none)" else chess.Move.from_uci(best)

    def suggest(self, board):
        """Engine's preferred move for the side to move, used for hints."""
        return self.play(board)

    def evaluate(self, board, think_time=0.3):
        """Full-strength look at the position: (cp, mate, best_move) for the
        side to move. cp is centipawns (None if mate is set); mate is moves to
        mate, negative if the side to move is getting mated. Used by explain.py."""
        self._send("setoption name Skill Level value 20")
        moves = " ".join(m.uci() for m in board.move_stack)
        self._send(f"position fen {board.root().fen()}" + (f" moves {moves}" if moves else ""))
        self._send(f"go movetime {int(think_time * 1000)}")
        cp = mate = None
        while True:
            line = self.inp.readline()
            if not line:
                raise RuntimeError("Stockfish closed the connection")
            words = line.split()
            if words[:1] == ["info"] and "score" in words:
                i = words.index("score")
                kind, value = words[i + 1], int(words[i + 2])
                cp, mate = (value, None) if kind == "cp" else (None, value)
            elif words[:1] == ["bestmove"]:
                best = None if words[1] == "(none)" else chess.Move.from_uci(words[1])
                break
        self._send(f"setoption name Skill Level value {self.skill}")
        return cp, mate, best

    def close(self):
        try:
            self._send("quit")
        except OSError:
            pass
        if self.proc:
            self.proc.wait(timeout=5)
        else:
            self.sock.close()
