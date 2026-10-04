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


TUNING_DEFAULTS = {
    "change_threshold": 25.0,   # how much a square must change to count as part of a move
    "min_fit": 10.0,            # how clearly the best move must stand out
    "still": 8.0,               # how little the board may move to count as still
    "marks": 8.0,               # how much a square must stand out to get a "?" mark
}


class NewGame(Exception):
    """Raised inside the loop to drop the current game and start another."""


class SetUp(Exception):
    """The page says the lesson position is set up, whatever the camera thinks."""


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
        self.hint = None                    # move suggested to the human this turn
        self.board_image = None             # straightened board for the web page
        self._new_game = queue.Queue(maxsize=1)
        self._typed = queue.Queue()
        self._hint = threading.Event()
        self._set_up = threading.Event()    # "It's set up" pressed during a lesson
        self.engine = None
        self.human = chess.WHITE
        self._mentioned = set()             # knocked pieces already mentioned
        # Tuning, adjustable live from the web page (sliders); see set_tuning
        self.tuning = dict(TUNING_DEFAULTS)
        self.reference = None               # last settled board image, for the live readout

    # ---- requests from the web page -------------------------------------

    def set_tuning(self, **values):
        """Change tuning values (any of TUNING_DEFAULTS); used from the next frame."""
        for k, v in values.items():
            if k in TUNING_DEFAULTS and v is not None:
                self.tuning[k] = float(v)
        self.cam.motion_threshold = self.tuning["still"]

    def request_new_game(self, colour="white", skill=5, hints=False, think=0.5,
                         change_threshold=None, min_fit=None, coach=False):
        self.set_tuning(change_threshold=change_threshold, min_fit=min_fit)
        settings = dict(colour=colour, skill=int(skill), hints=bool(hints), think=float(think),
                        coach=bool(coach))
        try:
            self._new_game.get_nowait()
        except queue.Empty:
            pass
        self._new_game.put(settings)

    def request_lesson(self, board, on_move, change_threshold=None, min_fit=None):
        """Watch the real board for a lesson move from `board`. on_move(move)
        is called with each move read and returns True if it was right."""
        self.set_tuning(change_threshold=change_threshold, min_fit=min_fit)
        self._replace(dict(lesson=board.copy(stack=False), on_move=on_move))

    def request_idle(self, status="Lesson: read the page, then press Next."):
        """Stop watching the board (e.g. a lesson step with nothing to play)."""
        self._replace(dict(idle=status))

    def request_set_up(self):
        self._set_up.set()

    def _replace(self, settings):
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
            "playing": self.settings is not None and "lesson" not in self.settings,
            "lesson": self.settings is not None and "lesson" in self.settings,
            "human": (self.settings or {}).get("colour", "white"),
            "turn": "white" if self.board.turn == chess.WHITE else "black",
            "last_move": last,
            "expected": self.expected.uci() if self.expected else None,
            "hint": self.hint.uci() if self.hint else None,
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
                if "idle" in settings:
                    self.settings = None
                    self.expected = None
                    self.hint = None
                    self._set_status(settings["idle"])
                elif "lesson" in settings:
                    self._lesson(settings)
                else:
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
                self._give_hint()
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

    def _give_hint(self):
        """Say the engine's suggestion and show it on the page until a move is made."""
        self.hint = self.engine.suggest(self.board)
        self.say("Hint: " + describe(self.board, self.hint))
        self.on_update(self.state())

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
        self.hint = None
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
                    self._give_hint()
                self._set_status("Your move.")
                self.say("Your move.")
                move, reference = self._read_move(reference)
                self.say("You played " + describe(self.board, move))
                self.hint = None
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

    # ---- lessons on the real board -------------------------------------

    def _lesson(self, s):
        """Wait for the lesson position to be on the board, then read moves
        until on_move says one was right."""
        self.settings = s
        self.board = s["lesson"]
        self.human = self.board.turn
        self.expected = None
        self.show_move(None)
        self._set_up.clear()
        self._set_status("Lesson: checking the position on the board...")
        if self.cam.H is None:
            self._set_status("Calibrate the board to use it for lessons.")
            raise NewGame(self._new_game.get())
        reference = self._lesson_position()
        self._show_board(reference)
        self._set_status("Lesson: make the move on the board.")
        while True:
            move, settled = self._read_move(reference)
            if s["on_move"](move):
                return
            self.say("Put the piece back where it was, then try again.")
            self._set_status("Lesson: put the piece back, then try again.")
            self._wait_for_undo(reference, settled)
            self._set_status("Lesson: make the move on the board.")

    def _lesson_position(self):
        """Wait until the camera sees pieces where the lesson needs them (or
        the page says it's set up). Returns the settled board image."""
        said = None
        thr = self.tuning["change_threshold"]

        def check():
            self._check_new_game_only()
            if self._set_up.is_set():
                raise SetUp()

        while True:
            try:
                img = self.cam.wait_until_still(check)
                if self.cam.realign():
                    img = self.cam.board()
                pieces = {sq: p.color for sq, p in self.board.piece_map().items()}
                extra, missing = occupancy_mismatches(img, pieces)
                if not extra and not missing:
                    return img
                message = self._setup_message(extra, missing)
                if message != said:
                    self.say(message)
                    said = message
                self._set_status("Lesson: set up the position shown on the page.")
                self.cam.wait_for_board_change(img, thr, check)
            except SetUp:
                self._set_up.clear()
                return self.cam.wait_until_still(self._check_new_game_only)

    def _setup_message(self, extra, missing):
        if len(extra) + len(missing) > 6:
            return ("Set up the position shown on the page. Press It's set up if the camera "
                    "doesn't notice.")
        groups = {}                         # "white pawn" -> squares
        for sq in missing:
            p = self.board.piece_at(sq)
            name = f"{'white' if p.color else 'black'} {chess.piece_name(p.piece_type)}"
            groups.setdefault(name, []).append(chess.square_name(sq))
        join = lambda xs: xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]
        parts = [f"put {'a ' + name if len(sqs) == 1 else name + 's'} on {join(sqs)}"
                 for name, sqs in groups.items()]
        if extra:
            parts.append("clear " + join([chess.square_name(sq) for sq in extra]))
        text = "; ".join(parts)
        return text[0].upper() + text[1:] + "."

    def _wait_for_undo(self, reference, wrong):
        """After a wrong lesson move, wait until the board changes again: back
        to how it was, or (the next read will tell) another move."""
        thr = self.tuning["change_threshold"]
        self.cam.wait_for_board_change(wrong, thr, self._check_new_game_only)

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
        Returns (move, settled_image). A move typed on the web page also counts.
        The same unreadable change isn't complained about twice, and a hand
        or other big change only once a turn."""
        t = self.tuning
        self.reference = reference
        misses = 0
        last_miss = None
        told_lots = False
        while True:
            try:
                settled = self.cam.wait_for_board_change(reference, t["change_threshold"], self._check)
            except TypedMove as tm:
                return tm.move, self.cam.wait_until_still(self._check_new_game_only)
            scores = change_scores(reference, settled)
            pieces = {sq: p.color for sq, p in self.board.piece_map().items()}
            extra, missing = occupancy_mismatches(settled, pieces, t["marks"])
            move, fit = infer_move(self.board, scores, t["min_fit"], (extra, missing))
            if move:
                touched = squares_touched(self.board, move)
                self._mentioned -= touched              # a piece moved there now: start afresh
                knocked = knocked_pieces(self.board, move, scores, missing, t["change_threshold"])
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
            changed = frozenset(sq for sq in range(64) if scores[sq] > t["change_threshold"])
            if changed == last_miss:
                continue                                # same as last time: already said
            last_miss = changed
            misses += 1
            if len(changed) > 8:
                if not (extra or missing):
                    # every piece is where it was: the light changed, not the
                    # board, so compare with how it looks now from here on
                    reference = self.reference = settled
                    last_miss = None
                elif not told_lots:
                    told_lots = True
                    self.say("Lots of the board changed. Is a hand or something else over it?")
                continue
            names = ", ".join(chess.square_name(sq) for sq in sorted(changed))
            self.say("I couldn't read that move. Please check the pieces are centred on their "
                     "squares." + (f" I saw changes on {names}." if names else ""))
            if misses >= 3:
                self.say("You can also type the move on the web page, for example e2e4.")
                misses = 0

    def calibrate_preview(self):
        """Straightened board with a grid, straight after calibrating."""
        frame = self.cam.latest()
        if frame is not None and self.cam.H is not None:
            self.board_image = draw_grid(warp(frame, self.cam.H))
