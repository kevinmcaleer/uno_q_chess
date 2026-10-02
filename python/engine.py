"""Talks UCI to the Stockfish chess engine.

On the UNO Q, Stockfish runs in its own container (the `stockfish` brick in
bricks/stockfish) and listens on TCP port 4000; every connection gets a fresh
Stockfish process. On a PC with Stockfish installed it is started directly
(unless STOCKFISH_HOST is set).
"""
import os
import shutil
import socket
import subprocess
import time

import chess

HOST = os.environ.get("STOCKFISH_HOST", "stockfish")
PORT = int(os.environ.get("STOCKFISH_PORT", "4000"))


class Engine:
    def __init__(self, skill=5, think_time=0.5, connect_timeout=600, on_wait=None):
        local = None if "STOCKFISH_HOST" in os.environ else (
            shutil.which("stockfish") or
            ("/usr/games/stockfish" if os.path.exists("/usr/games/stockfish") else None))
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
        self._send(f"setoption name Skill Level value {skill}")
        self._send("isready")
        self._wait_for("readyok")
        self.movetime = int(think_time * 1000)

    @staticmethod
    def _connect(timeout, on_wait):
        """The Stockfish container installs Stockfish the first time it starts,
        so keep trying for a while."""
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

    def close(self):
        try:
            self._send("quit")
        except OSError:
            pass
        if self.proc:
            self.proc.wait(timeout=5)
        else:
            self.sock.close()
