"""Offline test of the lessons: every step can be completed, every listed
move is legal, and wrong or illegal moves get a sensible answer.

  python3 test_lessons.py
"""
import chess

from lessons import LESSONS, Runner, _goal_moves, _parse


def check(name, ok, detail=""):
    print(f"{'ok  ' if ok else 'FAIL'} {name}{': ' + detail if detail else ''}")
    return ok


def walk_all():
    results = []
    r = Runner()
    for lesson in LESSONS:
        r.open(lesson["id"])
        problems = []
        while True:
            step = r.step
            goal = step.get("goal")
            for sq in r.highlights():
                chess.parse_square(sq)
            if goal:
                for text in goal.get("moves", []):
                    if not _parse(r.board, text):
                        problems.append(f"step {r.i}: {text} isn't legal in {r.board.fen()}")
                good = _goal_moves(r.board, goal)
                for text in step.get("wrong", {}):
                    m = _parse(r.board, text)
                    if not m or m in good:
                        problems.append(f"step {r.i}: wrong move {text} is illegal or correct")
                answer = r.answer()
                if not answer:
                    problems.append(f"step {r.i}: no correct move in {r.board.fen()}")
                    break
                i = r.i
                ok, message = r.try_move(answer)
                if not ok:
                    problems.append(f"step {i}: answer {answer} refused: {message}")
                    break
            else:
                if r.i + 1 == lesson_len(lesson):
                    break
                r.next()
            if r.finished or (r.i + 1 == lesson_len(lesson) and not r.step.get("goal")
                              and not r.wants_move and r.i == lesson_len(lesson) - 1
                              and not goal):
                break
        results.append(check(f"lesson '{lesson['title']}' ({lesson_len(lesson)} steps)",
                             not problems, "; ".join(problems)))
    return results


def lesson_len(lesson):
    return len(lesson["steps"])


def feedback():
    results = []
    r = Runner()
    r.open("pawn")
    ok, text = r.try_move("e2e5")
    results.append(check("illegal pawn move explained", not ok and "pawn can't" in text, text))
    ok, text = r.try_move("e2e4")
    results.append(check("correct move advances", ok and r.i == 1 and r.board.turn == chess.WHITE,
                         text))
    r.go(2)
    ok, text = r.try_move("e4f5")
    results.append(check("specific wrong-move answer", not ok and "knight is worth" in text, text))

    r.open("king")
    r.go(1)
    ok, text = r.try_move("e1d1")
    results.append(check("king can't walk into check", not ok and "check" in text, text))

    r.open("hanging")
    ok, text = r.try_move("e4c5")
    ok2, _ = r.try_move("e4g5")
    results.append(check("unsafe square refused, safe one accepted", not ok and ok2, text))

    r.open("opening-principles")
    r.try_move("e2e4")
    r.try_move("e7e5")
    ok, text = r.try_move("g1h3")
    results.append(check("knight on the rim", not ok and "rim" in text, text))

    r.open("forks")
    ok, text = r.try_move("b5c7")
    results.append(check("fork praised", ok and "rook falls" in text, text))

    r.open("pawn")
    r.go(4)
    ok, text = r.try_move("e7e8")              # clicked: promotes to a queen
    results.append(check("click promotes to a queen", ok, text))

    r.open("italian")
    r.go(3)                                     # carries on from earlier steps
    results.append(check("jumping into an opening rebuilds the position",
                         r.board.fen().startswith("rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP"), r.board.fen()))
    return results


if __name__ == "__main__":
    results = walk_all() + feedback()
    print(f"{sum(results)}/{len(results)} passed")
    raise SystemExit(0 if all(results) else 1)
