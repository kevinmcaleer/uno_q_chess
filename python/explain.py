"""Explain *why* a move is good or bad, in words a learner can follow.

Two layers:
  * Rules worked out with python-chess alone (no engine): a piece left
    hanging, a checkmate allowed or missed, a free capture missed, a fork,
    a pin, castling, development. These give the reasons.
  * Stockfish's evaluation before and after the move (optional): how much
    the move cost, which grades it Best / Good / Inaccuracy / Mistake /
    Blunder and, for a poor move, what would have been better.

`coach(engine, board, move)` does both and returns an Explanation whose
`.text` is ready to speak. `reasons_for(board, move)` gives the good points
of any move, e.g. to say why the computer played what it did.
"""
from dataclasses import dataclass, field

import chess

VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5,
          chess.QUEEN: 9, chess.KING: 100}

# Centipawns lost (vs the engine's best move) for each grade.
GOOD, INACCURACY, MISTAKE, BLUNDER = 50, 100, 250, 250
MATE_CP = 10000             # a forced mate counts as this many centipawns


@dataclass
class Reason:
    weight: int             # bigger = more important, said first
    text: str
    move: chess.Move = None     # the better move, for "you could have..." reasons


@dataclass
class Explanation:
    quality: str = ""       # "best", "good", "inaccuracy", "mistake", "blunder" or "" (no engine)
    loss: int = 0           # centipawns the move gave away
    best: chess.Move = None
    good: list = field(default_factory=list)    # Reasons
    bad: list = field(default_factory=list)     # Reasons
    text: str = ""

    @property
    def worth_saying(self):
        """Mistakes always; good moves only when there's a clear reason."""
        if self.quality in ("inaccuracy", "mistake", "blunder"):
            return bool(self.text)
        return any(r.weight >= 8 for r in self.good)


# ---- small helpers -------------------------------------------------------

def _name(board, square):
    piece = board.piece_at(square)
    return chess.piece_name(piece.piece_type) if piece else "pawn"


def _where(board, square):
    return f"{_name(board, square)} on {chess.square_name(square)}"


def _short(board, move):
    """'knight to f6', 'bishop takes on c6', 'castles' (board before the move)."""
    if board.is_castling(move):
        return "castling"
    verb = "takes on" if board.is_capture(move) else "to"
    return f"{_name(board, move.from_square)} {verb} {chess.square_name(move.to_square)}"


def _and(items):
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _after(board, move):
    b = board.copy(stack=False)
    b.push(move)
    return b


def _passed(board):
    """The same position with the other side to move (None if in check)."""
    if board.is_check():
        return None
    b = board.copy(stack=False)
    b.push(chess.Move.null())
    return b


def _gain(board, move):
    """Material the side to move wins outright with this capture, counting
    an immediate recapture by the cheapest defender (0 if not a capture)."""
    if not board.is_capture(move):
        return 0
    target = VALUES[board.piece_type_at(move.to_square) or chess.PAWN]
    after = _after(board, move)
    if not after.attackers(after.turn, move.to_square):
        return target
    return max(0, target - VALUES[board.piece_type_at(move.from_square)])


def _free_captures(board):
    """[(gain, move)] for the side to move, best first, gain > 0 only."""
    best = {}
    for move in board.legal_moves:
        g = _gain(board, move)
        if g > 0 and g > best.get(move.to_square, (0, None))[0]:
            best[move.to_square] = (g, move)
    return sorted(best.values(), key=lambda gm: -gm[0])


def _mates(board):
    return [m for m in board.legal_moves if _after(board, m).is_checkmate()]


def _fork_targets(board, square):
    """Enemy pieces the piece on `square` attacks that are worth more than it
    or undefended (bigger than a pawn). Needs two to be a fork."""
    piece = board.piece_at(square)
    enemy = not piece.color
    out = []
    for sq in board.attacks(square):
        target = board.piece_at(sq)
        if not target or target.color != enemy or target.piece_type == chess.PAWN:
            continue
        if (target.piece_type == chess.KING or VALUES[target.piece_type] > VALUES[piece.piece_type]
                or not board.attackers(enemy, sq)):
            out.append(sq)
    return out


def _is_fork(board, square):
    """The fork targets of the piece on `square`, if it forks two or more and
    can't simply be taken; else None."""
    targets = _fork_targets(board, square)
    if len(targets) < 2:
        return None
    piece = board.piece_at(square)
    attackers = board.attackers(not piece.color, square)
    if attackers:
        cheapest = min(VALUES[board.piece_type_at(a)] for a in attackers)
        if cheapest <= VALUES[piece.piece_type] or not board.attackers(piece.color, square):
            return None
    return targets


def _fork_names(board, targets):
    targets = sorted(targets, key=lambda t: -VALUES[board.piece_type_at(t)])
    return _and(_name(board, t) for t in targets)


# ---- what's good about a move -------------------------------------------

def reasons_for(board, move):
    """Good points of `move` (board before it), most important first, as
    phrases like 'forking the king and rook'."""
    after = _after(board, move)
    out = []
    if after.is_checkmate():
        return [Reason(200, "checkmate")]

    gain = _gain(board, move)
    if gain:
        victim = _where(board, move.to_square)
        if gain >= VALUES[board.piece_type_at(move.to_square) or chess.PAWN]:
            out.append(Reason(10 * gain, f"winning the {victim} for free"))
        else:
            out.append(Reason(10 * gain, f"winning the {victim} for a "
                                         f"{_name(board, move.from_square)}"))

    targets = _is_fork(after, move.to_square)
    if targets:
        out.append(Reason(40, f"forking the {_fork_names(after, targets)}"))

    enemy = after.turn
    king = after.king(enemy)
    pinned = set()
    for sq in chess.SquareSet(after.occupied_co[enemy]):
        if sq == king or after.piece_type_at(sq) == chess.PAWN:
            continue
        if after.is_pinned(enemy, sq) and move.to_square in after.pin(enemy, sq) \
                and not board.is_pinned(enemy, sq):
            out.append(Reason(25, f"pinning the {_where(after, sq)} to the king"))
            pinned.add(sq)

    if after.is_check():
        out.append(Reason(5, "giving check"))

    if board.is_castling(move):
        out.append(Reason(15, "getting the king to safety"))
    elif (board.piece_type_at(move.from_square) in (chess.KNIGHT, chess.BISHOP)
          and chess.square_rank(move.from_square) in (0, 7) and board.fullmove_number <= 10):
        out.append(Reason(8, f"bringing the {_name(board, move.from_square)} into play"))

    passed = _passed(after)                 # could it take something next move?
    if not gain and passed:
        before = {m.to_square for _, m in _free_captures(board)}
        for g, m in _free_captures(passed):
            if m.from_square == move.to_square and m.to_square not in before | pinned and g >= 3:
                out.append(Reason(9, f"attacking the {_where(after, m.to_square)}"))
                break
    return sorted(out, key=lambda r: -r.weight)


# ---- what's wrong with a move -------------------------------------------

def problems_with(board, move, them="your opponent"):
    """Sentences saying what `move` gets wrong, most serious first."""
    after = _after(board, move)
    if after.is_checkmate():
        return []
    out = []

    mates = _mates(after)
    if mates:
        out.append(Reason(100, f"That lets {them} checkmate with {_short(after, mates[0])}."))

    mine = _mates(board)
    if mine and move not in mine:
        out.append(Reason(90, f"You had checkmate with {_short(board, mine[0])}.", mine[0]))

    # Pieces newly left to be taken.
    passed = _passed(board)
    already = {m.to_square: g for g, m in _free_captures(passed)} if passed else {}
    captured = _gain(board, move) or (VALUES[board.piece_type_at(move.to_square)]
                                      if board.is_capture(move) and board.piece_at(move.to_square)
                                      else 0)
    for g, m in _free_captures(after):
        sq = m.to_square
        if sq == move.to_square:
            sq_before = move.from_square
            g -= captured             # a trade isn't a blunder
        else:
            sq_before = sq
        if g <= 0 or already.get(sq_before, 0) >= g:
            continue
        piece = _where(after, sq)
        if not after.attackers(not after.turn, sq):
            text = f"That leaves your {piece} undefended, and {them} can take it."
        else:
            text = f"Your {piece} can be won by the {_where(after, m.from_square)}."
        out.append(Reason(10 * g, text))
        break

    # A fork it allows.
    already_forks = set()
    if passed:
        for m in passed.legal_moves:
            if _is_fork(_after(passed, m), m.to_square):
                already_forks.add(m)
    for m in after.legal_moves:
        if m in already_forks or after.is_capture(m):
            continue
        a2 = _after(after, m)
        targets = _is_fork(a2, m.to_square)
        if targets:
            out.append(Reason(35, f"That lets {them} fork your {_fork_names(a2, targets)} "
                                  f"with {_short(after, m)}."))
            break

    # A free capture it missed.
    chances = _free_captures(board)
    if chances and chances[0][0] >= 2 and _gain(board, move) < chances[0][0]:
        g, m = chances[0]
        out.append(Reason(8 * g, f"You could have won the {_where(board, m.to_square)} "
                                 f"with your {_name(board, m.from_square)}.", m))
    return sorted(out, key=lambda r: -r.weight)


# ---- with the engine ----------------------------------------------------

def _cp(score):
    """(cp, mate) from the side to move's point of view -> centipawns."""
    cp, mate = score
    if mate is not None:
        return MATE_CP - 10 * abs(mate) if mate > 0 else -MATE_CP + 10 * abs(mate)
    return max(-2000, min(2000, cp))


def grade(loss, was_best):
    if was_best or loss <= 10:
        return "best"
    if loss < GOOD:
        return "good"
    if loss < INACCURACY:
        return "inaccuracy"
    if loss < MISTAKE:
        return "mistake"
    return "blunder"


OPENERS = {"best": "Great move", "good": "Good move", "inaccuracy": "Not quite the best",
           "mistake": "That's a mistake", "blunder": "Oh no, that's a blunder"}


def explain(board, move, before=None, after=None, best=None, them="your opponent"):
    """Explain `move` (board before it). `before` and `after` are engine
    scores (cp, mate) for the side to move before and after the move, and
    `best` the engine's best move; leave them out for rules only."""
    e = Explanation(best=best)
    e.good = reasons_for(board, move)
    e.bad = problems_with(board, move, them)
    if before is not None and after is not None:
        e.loss = max(0, _cp(before) + _cp(after))     # `after` is from the opponent's side
        e.quality = grade(e.loss, best == move)
    e.text = _text(board, move, e)
    return e


def _text(board, move, e):
    after = _after(board, move)
    if after.is_checkmate():
        return "Checkmate! Well done."
    good = [r.text for r in e.good if r.weight >= 8][:2]
    if e.quality in ("best", "good") or (not e.quality and not e.bad):
        opener = OPENERS.get(e.quality, "")
        if good:
            return f"{opener or 'Nice'}: {_and(good)}." if opener else f"{_and(good).capitalize()}."
        return f"{opener}." if opener else ""

    parts = [OPENERS[e.quality] + "." if e.quality else ""]
    if e.bad:
        parts.append(e.bad[0].text)
    said = e.bad and e.bad[0].move == e.best
    if e.best and e.best != move and not said and e.quality in ("inaccuracy", "mistake", "blunder"):
        why = [r.text for r in reasons_for(board, e.best) if r.weight >= 8][:1]
        better = f"Better was {_short(board, e.best)}"
        parts.append(better + (", " + why[0] + "." if why else "."))
    return " ".join(p for p in parts if p)


def coach(engine, board, move, them="your opponent", think_time=0.3):
    """Ask Stockfish about `move` (board before it) and explain it."""
    cp, mate, best = engine.evaluate(board, think_time)
    after_board = _after(board, move)
    if after_board.is_checkmate():
        after = (None, 0)                   # mated: worst possible for them
    elif after_board.is_game_over():
        after = (0, None)                   # draw
    else:
        after = engine.evaluate(after_board, think_time)[:2]
    return explain(board, move, (cp, mate), after, best, them)
