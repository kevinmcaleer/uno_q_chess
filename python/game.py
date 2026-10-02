"""The game loop: watch the board, read each move, let Stockfish reply.

Runs in its own thread. The web page talks to it through the request_*
methods, which are safe to call from any thread."""
import queue
import threading

import chess

from announce import describe, draw_move
from detector import infer_move, knocked_pieces, squares_touched
from explain import coach, reasons_for
from vision import change_scores, draw_grid, occupancy_mismatches, warp


class NewGame(Exception):
    """Raised inside the loop to drop the current game and start another."""


class TypedMove(Exception):
    def __init__(self, move):
        self.move = move


class Game:
    def __init__(self, cam, make_engine, say, on_update, show_move=lambda move: None):
        self.cam = cam
        self.make_engine = make_engine      # (skill, think) -> Engine
        self.say = say                      # text -> None
        self.on_update = on_update          # state dict -> None
        self.show_move = show_move          # chess.Move or None -> None (LED matrix)
        self.board = chess.Board()
        self.settings = None
        self.status = "Calibrate the board, then start a new game."
        self.expected = None                # computer's move the human must make for it
        self.board_image = None             # straightened board for the web page
        self._new_game = queue.Queue(maxsize=1)
        self._typed = queue.Queue()
        self._hint = threading.Event()
        self.engine = None
        self.human = chess.WHITE
        self._mentioned = set()             # knocked pieces already mentioned

    # ---- requests from the web page -------------------------------------

    def request_new_game(self, colour="white", skill=5, hints=False, think=0.5,
                         change_threshold=25.0, min_fit=10.0, coach=False):
        settings = dict(colour=colour, skill=int(skill), hints=bool(hints), think=float(think),
                        coach=bool(coach),
                        change_threshold=float(change_threshold), min_fit=float(min_fit))
        try:
            self._new_game.get_nowait()
        except queue.Empty:
            pass
        self._new_game.put(settings)

    def request_typed_move(self, text):
        self._typed.put(text.strip())

    def request_hint(self):
        self._hint.set()

    def state(self):
        last = self.board.move_stack[-1].uci() if self.board.move_stack else None
        return {
            "fen": self.board.fen(),
            "status": self.status,
            "playing": self.settings is not None,
            "human": self.settings["colour"] if self.settings else "white",
            "turn": "white" if self.board.turn == chess.WHITE else "black",
            "last_move": last,
            "expected": self.expected.uci() if self.expected else None,
            "moves": self._san_moves(),
            "calibrated": self.cam.H is not None,
        }

    def _san_moves(self):
        b = chess.Board()
        out = []
        for m in self.board.move_stack:
            out.append(b.san(m))
            b.push(m)
        return out

    # ---- main loop ------------------------------------------------------

    def run(self):
        settings = self._new_game.get()
        while True:
            try:
                self._play(settings)
                settings = self._new_game.get()      # game over: wait for the next one
            except NewGame as e:
                settings = e.args[0]
            except Exception as e:                   # keep the app alive, show what went wrong
                self.settings = None
                self._set_status(f"Error: {e}")
                self.say(f"Something went wrong: {e}")
                settings = self._new_game.get()
            finally:
                if self.engine:
                    self.engine.close()
                    self.engine = None

    def _check(self):
        """Called on every camera frame while we wait for the board."""
        try:
            raise NewGame(self._new_game.get_nowait())
        except queue.Empty:
            pass
        if self._hint.is_set():
            self._hint.clear()
            if self.engine and self.board.turn == self.human and not self.board.is_game_over():
                self.say("Hint: " + describe(self.board, self.engine.suggest(self.board)))
        try:
            text = self._typed.get_nowait()
        except queue.Empty:
            return
        try:
            raise TypedMove(self.board.parse_uci(text.lower()))
        except ValueError:
            try:
                raise TypedMove(self.board.parse_san(text))
            except ValueError:
                self.say(f"{text} isn't a legal move here.")

    def _check_new_game_only(self):
        try:
            raise NewGame(self._new_game.get_nowait())
        except queue.Empty:
            pass

    def _set_status(self, text):
        self.status = text
        self.on_update(self.state())

    def _show_board(self, img, move=None):
        img = draw_grid(img)
        self.board_image = draw_move(img, move) if move else img

    def _play(self, s):
        self.settings = s
        self.human = chess.WHITE if s["colour"] == "white" else chess.BLACK
        self.board = chess.Board()
        self.expected = None
        self._mentioned = set()
        self.show_move(None)
        if self.cam.H is None:
            self.settings = None
            self._set_status("Calibrate the board first, then start a new game.")
            raise NewGame(self._new_game.get())

        self._set_status("Starting Stockfish...")
        self.engine = self.make_engine(
            s["skill"], s["think"],
            on_wait=lambda: self._set_status(
                "Downloading Stockfish (first game only, needs internet)..."))

        self.say("Set up the starting position and take your hands away.")
        self._set_status("Waiting for the board to settle.")
        reference = self.cam.wait_until_still(self._check_new_game_only)
        if self.cam.realign():
            reference = self.cam.board()
        self._show_board(reference)
        self.say("Board ready.")

        while not self.board.is_game_over():
            if self.board.turn == self.human:
                if s["hints"]:
                    self.say("Hint: " + describe(self.board, self.engine.suggest(self.board)))
                self._set_status("Your move.")
                self.say("Your move.")
                move, reference = self._read_move(reference)
                self.say("You played " + describe(self.board, move))
                if s.get("coach"):
                    self._coach(move)
                self.board.push(move)
            else:
                self._set_status("Thinking...")
                self.expected = self.engine.play(self.board)
                text = describe(self.board, self.expected)
                why = reasons_for(self.board, self.expected) if s.get("coach") else []
                if why and why[0].weight >= 8:
                    text += ", " + why[0].text.replace("getting the king", "getting my king")
                self._show_board(reference, self.expected)
                self.show_move(self.expected)
                self._set_status(f"Please play my move: {text}.")
                self.say("I play " + text + ". Please make that move for me.")
                while True:
                    move, settled = self._read_move(reference)
                    if move == self.expected:
                        break
                    self.say(f"That looks like {describe(self.board, move)}. "
                             f"Please put it back and play {text}.")
                reference = settled
                self.board.push(move)
                self.expected = None
            self._show_board(reference)
            self.on_update(self.state())
            if self.board.is_check():
                self.say("Check.")

        self.say(f"Game over: {self.board.result()}")
        self._set_status(f"Game over: {self.board.result()}. Start a new game when you're ready.")
        self.settings = None

    def _coach(self, move):
        """Say why the human's move was good or bad (board before the move).
        Quiet for ordinary moves; a problem here never stops the game."""
        self._set_status("Checking your move...")
        try:
            e = coach(self.engine, self.board, move, them="me")
        except Exception as err:
            self.say(f"I couldn't check that move: {err}")
            return
        if e.worth_saying:
            self.say(e.text)

    def _read_move(self, reference):
        """Wait for the board to change and settle, then work out the move.
        Returns (move, settled_image). A move typed on the web page also counts."""
        s = self.settings
        misses = 0
        while True:
            try:
                settled = self.cam.wait_for_board_change(reference, s["change_threshold"], self._check)
            except TypedMove as t:
                return t.move, self.cam.wait_until_still(self._check_new_game_only)
            scores = change_scores(reference, settled)
            pieces = {sq: p.color for sq, p in self.board.piece_map().items()}
            extra, missing = occupancy_mismatches(settled, pieces)
            move, fit = infer_move(self.board, scores, s["min_fit"], (extra, missing))
            if move:
                touched = squares_touched(self.board, move)
                self._mentioned -= touched              # a piece moved there now: start afresh
                knocked = knocked_pieces(self.board, move, scores, missing, s["change_threshold"])
                if knocked is None:
                    # most pieces changed: the board slid, so line the grid up
                    # again (quietly unless it actually moves)
                    if self.cam.realign(force=True):
                        settled = self.cam.board()
                    return move, settled
                new = [sq for sq in knocked if sq not in self._mentioned][:2]
                if new:
                    self._mentioned |= set(new)
                    names = " and ".join(chess.square_name(sq) for sq in new)
                    self.say(f"The piece on {names} looks knocked. Centre it when you can.")
                return move, settled
            misses += 1
            odd = sorted(set(extra) | set(missing))
            where = (" Have a look at " + ", ".join(chess.square_name(sq) for sq in odd) + "."
                     if odd else "")
            self.say("I couldn't read that move. Please check the pieces are centred on their "
                     "squares." + where)
            if misses >= 3:
                self.say("You can also type the move on the web page, for example e2e4.")
                misses = 0

    def calibrate_preview(self):
        """Straightened board with a grid, straight after calibrating."""
        frame = self.cam.latest()
        if frame is not None and self.cam.H is not None:
            self.board_image = draw_grid(warp(frame, self.cam.H))
