"""Work out which legal move was played from per-square change scores.

No piece recognition needed: we know the position before the move, so we
only have to ask "which legal move explains the squares that changed?"."""
import chess


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


def infer_move(board, scores, min_fit=10.0):
    """Return (move, fit) for the legal move that best explains the changes,
    or (None, fit) if nothing fits well enough.

    fit = weakest change on the move's own squares minus the strongest change
    anywhere else. A real move scores high on every square it touches and
    leaves the rest of the board quiet."""
    best, best_fit = None, float("-inf")
    for move in board.legal_moves:
        if move.promotion not in (None, chess.QUEEN):
            continue                                    # assume queen promotion
        touched = squares_touched(board, move)
        inside = min(scores[s] for s in touched)
        outside = max((scores[s] for s in range(64) if s not in touched), default=0.0)
        fit = inside - outside
        if fit > best_fit:
            best, best_fit = move, fit
    if best is None or best_fit < min_fit:
        return None, best_fit
    return best, best_fit
