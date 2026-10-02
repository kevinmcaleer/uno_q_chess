"""Work out which legal move was played from per-square change scores.

No piece recognition needed: we know the position before the move, so we
only have to ask "which legal move explains the squares that changed?"."""
import chess
import numpy as np


def squares_touched(board, move):
    touched = {move.from_square, move.to_square}
    if board.is_castling(move):
        rank = chess.square_rank(move.from_square)
        if chess.square_file(move.to_square) == 6:      # king side
            touched |= {chess.square(7, rank), chess.square(5, rank)}
        else:                                           # queen side
            touched |= {chess.square(0, rank), chess.square(3, rank)}
    if board.is_en_passant(move):
        touched.add(chess.square(chess.square_file(move.to_square),
                                 chess.square_rank(move.from_square)))
    return touched


def occupancy_change(board, move):
    """(squares that gain a piece, squares that lose one) when `move` is played."""
    before = set(board.piece_map())
    b = board.copy(stack=False)
    b.push(move)
    after = set(b.piece_map())
    return after - before, before - after


def infer_move(board, scores, min_fit=10.0, occupancy=None):
    """Return (move, fit) for the legal move that best explains the changes,
    or (None, fit) if nothing fits well enough.

    fit = weakest change on the move's own squares minus the strongest change
    anywhere else. A real move scores high on every square it touches and
    leaves the rest of the board quiet.

    occupancy: (squares that now look occupied but were empty, squares that
    now look empty but had a piece), from vision.occupancy_mismatches on the
    settled image. With it, a move must also explain which squares emptied,
    and a piece that was knocked but is still on its square doesn't
    count against the fit, so a nudged neighbour doesn't spoil the reading.
    If no move agrees with the occupancy, the plain fit decides among the
    moves whose emptied squares look empty."""
    candidates = []
    for move in board.legal_moves:
        if move.promotion not in (None, chess.QUEEN):
            continue                                    # assume queen promotion
        candidates.append((move, squares_touched(board, move)))

    def fit(touched, ignore=frozenset()):
        inside = min(scores[s] for s in touched)
        outside = max((scores[s] for s in range(64) if s not in touched and s not in ignore),
                      default=0.0)
        return inside - outside

    if occupancy is not None:
        extra, missing = set(occupancy[0]), set(occupancy[1])
        # pieces that should still be there and still look it: knocks allowed
        still_there = set(board.piece_map()) - missing
        # Every square the move empties must look empty, and nothing may look
        # filled or emptied away from the move's own squares. (On those, a
        # capture swaps a piece's colour, which the occupancy check, judging
        # by the old piece, can read as empty, so they aren't held to it.)
        agreeing = [(m, t) for m, t in candidates
                    if occupancy_change(board, m)[1] <= missing and (extra | missing) <= t]
        if agreeing:
            best, best_fit = max(((m, fit(t, still_there)) for m, t in agreeing),
                                 key=lambda mf: mf[1])
            if best_fit >= min_fit:
                return best, best_fit

        # Otherwise a knocked piece has strayed onto another square. Still
        # insist the squares the move empties look empty: reading the wrong
        # move is worse than asking the player to tidy up.
        candidates = [(m, t) for m, t in candidates if occupancy_change(board, m)[1] <= missing]

    best, best_fit = None, float("-inf")
    for move, touched in candidates:
        f = fit(touched)
        if f > best_fit:
            best, best_fit = move, f
    if best is None or best_fit < min_fit:
        return None, best_fit
    return best, best_fit


def knocked_pieces(board, move, scores, missing, threshold, most=3):
    """Pieces that look knocked by `move`: still on their squares (not in
    `missing`) and not part of the move, but changed a lot more than the
    other pieces did. Returns None if more than `most` pieces changed like
    that: then the whole board shifted (or the light changed), not a few
    pieces, and nothing should be said about knocks."""
    touched = squares_touched(board, move)
    others = [sq for sq in board.piece_map() if sq not in touched and sq not in missing]
    if not others:
        return []
    typical = float(np.median([scores[sq] for sq in others]))
    knocked = [sq for sq in others if scores[sq] > threshold and scores[sq] > typical + threshold]
    many = sum(scores[sq] > threshold for sq in others)
    if many > most:
        return None
    return knocked
