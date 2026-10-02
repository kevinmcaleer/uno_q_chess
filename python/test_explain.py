"""Offline test of the move explanations on classic positions.

  python3 test_explain.py     # rules always; the Stockfish part needs it installed
"""
import chess

from engine import Engine, find_local
from explain import coach, explain, problems_with, reasons_for


def board_after(*san, fen=chess.STARTING_FEN):
    b = chess.Board(fen)
    for m in san:
        b.push_san(m)
    return b


def check(name, text, *wanted, absent=()):
    low = text.lower()
    ok = all(w in low for w in wanted) and not any(a in low for a in absent)
    print(f"{'ok  ' if ok else 'FAIL'} {name}: {text}")
    return ok


def texts(reasons):
    return " | ".join(r.text for r in reasons)


def rules():
    results = []
    scholar = board_after("e4", "e5", "Bc4", "Nc6", "Qh5")

    b = scholar
    results.append(check("allows mate", texts(problems_with(b, b.parse_san("Nf6"))),
                         "checkmate with queen takes on f7"))

    b = board_after("Nf6", fen=scholar.fen())
    results.append(check("missed mate", texts(problems_with(b, b.parse_san("d3"))),
                         "you had checkmate with queen takes on f7"))

    b = board_after("e4", "e5")
    results.append(check("hangs a piece", texts(problems_with(b, b.parse_san("Ba6"))),
                         "bishop on a6"))

    b = board_after("e4", "e5", "Nf3", "Nc6", "Bb5", "a6")
    results.append(check("a trade is not a blunder", texts(problems_with(b, b.parse_san("Bxc6"))),
                         absent=("bishop on c6",)))

    b = chess.Board("4k3/8/8/3q4/8/2N5/8/4K3 w - - 0 1")
    results.append(check("missed free capture", texts(problems_with(b, b.parse_san("Ke2"))),
                         "won the queen on d5 with your knight"))

    b = chess.Board("r1r1k3/8/8/1N6/8/8/8/4K3 b - - 0 1")
    results.append(check("allows a fork", texts(problems_with(b, b.parse_san("Rd8"))),
                         "fork your king and rook", "knight to c7"))
    results.append(check("safe move allows no fork", texts(problems_with(b, b.parse_san("Rab8"))),
                         absent=("fork",)))

    b = chess.Board("r3k3/8/8/1N6/8/8/8/4K3 w - - 0 1")
    results.append(check("finds a fork", texts(reasons_for(b, b.parse_san("Nc7+"))),
                         "forking the king and rook"))

    b = chess.Board("4k3/8/2n5/8/8/8/8/3BK3 w - - 0 1")
    results.append(check("finds a pin", texts(reasons_for(b, b.parse_san("Ba4"))),
                         "pinning the knight on c6 to the king"))

    b = chess.Board("4k3/8/8/3q4/8/2N5/8/4K3 w - - 0 1")
    results.append(check("wins material", texts(reasons_for(b, b.parse_san("Nxd5"))),
                         "winning the queen on d5 for free"))

    b = board_after("e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5")
    results.append(check("castling", texts(reasons_for(b, b.parse_san("O-O"))), "king to safety"))

    # Full sentences, with made-up engine scores.
    b = chess.Board("r3k3/8/8/1N6/8/8/8/4K3 w - - 0 1")
    m = b.parse_san("Nc7+")
    results.append(check("best move text", explain(b, m, (0, None), (-500, None), m).text,
                         "great move", "forking the king and rook"))

    b = scholar
    results.append(check("blunder text", explain(b, b.parse_san("Nf6"), (-30, None), (None, 1),
                                                 b.parse_san("g6"), them="me").text,
                         "blunder", "lets me checkmate", "better was pawn to g6"))
    return results


def with_engine():
    path = find_local()
    if not path:
        print("skip Stockfish checks: not installed")
        return []
    engine = Engine(skill=3, path=path)
    results = []
    try:
        b = board_after("e4", "e5", "Bc4", "Nc6", "Qh5")
        e = coach(engine, b, b.parse_san("Nf6"), them="me")
        results.append(check("engine grades scholar's blunder", f"[{e.quality}] {e.text}",
                             "[blunder]", "checkmate"))

        b = chess.Board()
        e = coach(engine, b, b.parse_san("e4"))
        results.append(check("engine likes 1.e4", f"[{e.quality}] {e.text}",
                             absent=("mistake", "blunder")))

        b = chess.Board("4k3/8/8/3q4/8/2N5/8/4K3 w - - 0 1")
        e = coach(engine, b, b.parse_san("Ke2"))
        results.append(check("engine: missed queen", f"[{e.quality}] {e.text}",
                             "[blunder]", "queen on d5"))
        # Skill level is restored after evaluating.
        results.append(check("skill restored", str(engine.skill), "3"))
    finally:
        engine.close()
    return results


if __name__ == "__main__":
    results = rules() + with_engine()
    print(f"{sum(results)}/{len(results)} passed")
    raise SystemExit(0 if all(results) else 1)
