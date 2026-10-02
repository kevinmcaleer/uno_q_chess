"""Chess lessons: the pieces and how they move, simple strategy, tactics and
famous openings. Each lesson is a list of steps; a step either explains
something (press Next) or asks for a move, which can be made by clicking on
the web page or on the real board (the camera reads it, see game.py).

Step fields:
  text   what to read or do (shown and spoken)
  fen    the position (leave out to carry on from the previous step)
  goal   what counts as a correct move (leave out for a read-only step):
           {"moves": [...]}   one of these (SAN like "Nf3" or UCI like "g1f3")
           {"from": "d4"}     any legal move of the piece on that square
           {"piece": "B"}     any legal move of a piece of that kind (side to move)
           {"check": True}    any move that gives check
           {"mate": True}     any move that gives checkmate
           {"safe": "e4"}     move the piece on that square somewhere it can't be won
  ok     said after a correct move (default: "Correct!" plus why, if it's clear)
  wrong  {move: text} said after particular wrong moves
  hint   said after any other wrong move
  show   squares to highlight; "moves:d4" highlights where the piece on d4 can go

Positions in the early lessons have no kings, to keep them simple; that's
fine for python-chess and for the camera.
"""
import threading

import chess

from explain import _free_captures, problems_with, reasons_for

EMPTY = "8/8/8/8/8/8/8/8 w - - 0 1"
START = chess.STARTING_FEN


def _opening(id, title, intro, moves, outro):
    """An opening as steps: the player makes every move, both colours."""
    steps = [{"text": intro, "fen": START}]
    for san, text in moves:
        steps.append({"text": text, "goal": {"moves": [san]}})
    steps.append({"text": outro})
    return {"id": id, "section": "Openings", "title": title, "steps": steps}


LESSONS = [
    # ---- the basics ------------------------------------------------------
    {"id": "board", "section": "Chess basics", "title": "The board", "steps": [
        {"fen": EMPTY, "show": ["e4"],
         "text": "A chess board has 64 squares: 8 rows called ranks, numbered 1 to 8, and 8 "
                 "columns called files, lettered a to h. Every square has a name made of its file "
                 "and rank. The highlighted square is e4. Set the board up so the corner square on "
                 "your right is light: 'light on the right'."},
        {"fen": START,
         "text": "This is the starting position. Each side has 8 pawns, 2 rooks, 2 knights, "
                 "2 bishops, a queen and a king. The queen starts on her own colour: the white "
                 "queen on the light square d1, the black queen on the dark square d8. White "
                 "always moves first."},
        {"text": "Let's use a square name. Move the white pawn from e2 to e4.",
         "goal": {"moves": ["e4"]}, "show": ["e2", "e4"],
         "ok": "That's e4, one of the most popular first moves in chess."},
    ]},
    {"id": "pawn", "section": "Chess basics", "title": "The pawn", "steps": [
        {"fen": "8/8/8/8/8/8/4P3/8 w - - 0 1", "show": ["moves:e2"],
         "text": "Pawns move straight forward, one square at a time, but on its very first move "
                 "a pawn may move two squares. Move this pawn two squares, to e4.",
         "goal": {"moves": ["e2e4"]}, "hint": "Two squares straight up the board: e2 to e4.",
         "ok": "Two squares, because it was the pawn's first move."},
        {"text": "From now on it can only move one square at a time. Move it to e5.",
         "goal": {"moves": ["e4e5"]}, "show": ["moves:e4"]},
        {"fen": "8/8/8/3n1p2/4P3/8/8/8 w - - 0 1", "show": ["d5", "f5"],
         "text": "Pawns capture differently from how they move: one square diagonally forward. "
                 "They can't capture straight ahead. Capture the black knight.",
         "goal": {"moves": ["e4d5"]},
         "wrong": {"e4f5": "That takes a pawn. The knight is worth three pawns, so it's the "
                           "better catch."},
         "ok": "Pawns attack diagonally, so they guard the squares in front of them to each side."},
        {"fen": "8/8/8/4p3/4P3/8/8/8 w - - 0 1", "show": ["e4", "e5"],
         "text": "A pawn with a piece straight in front of it is stuck. These two pawns block "
                 "each other: neither can move forward, and there's nothing to capture."},
        {"fen": "8/4P3/8/8/8/8/8/8 w - - 0 1", "show": ["e8"],
         "text": "When a pawn reaches the far side of the board it is promoted: you swap it for "
                 "a queen, rook, bishop or knight of your colour. Nearly everyone picks a queen. "
                 "Push the pawn to e8.",
         "goal": {"moves": ["e7e8q"]},
         "ok": "A new queen! On the real board, swap the pawn for a queen."},
        {"fen": "8/8/8/3pP3/8/8/8/8 w - d6 0 1", "show": ["d5", "d6"],
         "text": "One last pawn rule, en passant ('in passing'). If an enemy pawn moves two "
                 "squares and lands right beside your pawn, you may capture it as if it had moved "
                 "only one, but only on the very next move. Black has just played d7 to d5. "
                 "Capture it en passant by moving your pawn to d6.",
         "goal": {"moves": ["e5d6"]},
         "ok": "That's en passant. The black pawn on d5 comes off the board."},
    ]},
    {"id": "knight", "section": "Chess basics", "title": "The knight", "steps": [
        {"fen": "8/8/8/8/3N4/8/8/8 w - - 0 1", "show": ["moves:d4"],
         "text": "The knight moves in an L shape: two squares in one direction, then one square "
                 "to the side. The highlighted squares are where this knight can go. Move it to "
                 "any of them.",
         "goal": {"from": "d4"},
         "ok": "A knight always lands on a square of the opposite colour to the one it left."},
        {"fen": "8/8/8/8/8/8/PPPP4/1N6 w - - 0 1", "show": ["moves:b1"],
         "text": "The knight is the only piece that can jump over others. Jump from b1 to c3, "
                 "straight over the pawns.",
         "goal": {"moves": ["b1c3"]}},
        {"fen": "8/8/2r5/8/3N4/8/8/8 w - - 0 1", "show": ["moves:d4"],
         "text": "A knight captures by landing on an enemy piece. Capture the rook.",
         "goal": {"moves": ["d4c6"]}},
    ]},
    {"id": "bishop", "section": "Chess basics", "title": "The bishop", "steps": [
        {"fen": "8/8/8/8/8/8/8/2B5 w - - 0 1", "show": ["moves:c1"],
         "text": "Bishops move any distance diagonally. Because of that, a bishop stays on the "
                 "same colour of square all game. Move this one all the way to h6.",
         "goal": {"moves": ["c1h6"]}},
        {"fen": "8/6r1/8/8/3P4/8/8/B7 w - - 0 1", "show": ["moves:a1"],
         "text": "Bishops can't jump. This one is blocked by its own pawn on d4, so it can't "
                 "reach the rook on g7. Clear the way: move the pawn to d5.",
         "goal": {"moves": ["d4d5"]}},
        {"text": "Now the diagonal is open. Capture the rook with the bishop.",
         "goal": {"moves": ["a1g7"]}, "show": ["moves:a1"]},
    ]},
    {"id": "rook", "section": "Chess basics", "title": "The rook", "steps": [
        {"fen": "8/8/8/8/8/8/8/R7 w - - 0 1", "show": ["moves:a1"],
         "text": "Rooks move any distance in a straight line: up, down, left or right. Move the "
                 "rook to the top of the board, a8.",
         "goal": {"moves": ["a1a8"]}},
        {"text": "Now slide it along the top rank to h8.", "goal": {"moves": ["a8h8"]},
         "show": ["moves:a8"]},
        {"fen": "8/8/8/3p4/8/8/3R4/8 w - - 0 1", "show": ["moves:d2"],
         "text": "Capture the black pawn with the rook.", "goal": {"moves": ["d2d5"]}},
    ]},
    {"id": "queen", "section": "Chess basics", "title": "The queen", "steps": [
        {"fen": "8/8/8/8/3Q4/8/8/8 w - - 0 1", "show": ["moves:d4"],
         "text": "The queen is the most powerful piece. She moves like a rook and a bishop "
                 "together: any distance in a straight line or along a diagonal. Move her "
                 "anywhere you like.",
         "goal": {"from": "d4"}},
        {"fen": "r7/8/8/8/8/8/8/7Q w - - 0 1",
         "text": "Capture the rook in one move.", "goal": {"moves": ["h1a8"]},
         "hint": "Look along the long diagonal from h1."},
    ]},
    {"id": "king", "section": "Chess basics", "title": "The king and check", "steps": [
        {"fen": "8/8/8/8/4K3/8/8/8 w - - 0 1", "show": ["moves:e4"],
         "text": "The king moves one square in any direction. It's slow, but it's the most "
                 "important piece: if your king is trapped, you lose. Move it one square.",
         "goal": {"from": "e4"}},
        {"fen": "3r4/8/8/8/8/8/8/4K3 w - - 0 1", "show": ["moves:e1"],
         "text": "A king may never move onto a square an enemy piece attacks. The black rook "
                 "controls the whole d-file. Move your king, but keep it off the d-file.",
         "goal": {"from": "e1"}},
        {"fen": "4k3/8/8/8/8/8/8/R3K3 w - - 0 1",
         "text": "Attacking the enemy king is called check, and the other side must get out of "
                 "check straight away. Put the black king in check with your rook.",
         "goal": {"check": True}, "hint": "The rook attacks along ranks and files."},
        {"fen": "6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1",
         "text": "If a king is in check and there's no way out, that's checkmate and the game "
                 "is over. Find checkmate in one move.",
         "goal": {"mate": True},
         "ok": "Checkmate! This is a back-rank mate: the black king is boxed in by its own "
               "pawns."},
    ]},
    {"id": "castling", "section": "Chess basics", "title": "Castling", "steps": [
        {"fen": "r3k2r/pppppppp/8/8/8/8/PPPPPPPP/R3K2R w KQkq - 0 1", "show": ["e1", "g1", "h1", "f1"],
         "text": "Castling tucks your king away and brings a rook into play in one move. The "
                 "king moves two squares towards a rook, and that rook hops over to the square "
                 "on the king's other side. You can only castle if neither piece has moved yet, "
                 "the squares between them are empty, and your king isn't in check or passing "
                 "through an attacked square. Castle on the king side: move the king from e1 to "
                 "g1, then the rook from h1 to f1.",
         "goal": {"moves": ["O-O"]},
         "ok": "Castled! The king is safe in the corner and the rook is heading for the centre."},
        {"show": ["e8", "c8", "a8", "d8"],
         "text": "Black castles on the queen side: king from e8 to c8, then rook from a8 to d8.",
         "goal": {"moves": ["O-O-O"]}},
    ]},

    # ---- strategy ------------------------------------------------------------
    {"id": "values", "section": "Strategy", "title": "What the pieces are worth", "steps": [
        {"fen": START,
         "text": "Pieces have rough values, counted in pawns: a pawn is 1, a knight 3, a bishop "
                 "3, a rook 5 and a queen 9. The king is priceless. Use these numbers to decide "
                 "if a trade is good: giving up a knight (3) to win a rook (5) gains you 2."},
        {"fen": "3k4/3p4/8/8/r7/8/8/3Q2K1 w - - 0 1",
         "text": "Your queen can take the pawn on d7 or the rook on a4. Which is the better "
                 "capture?",
         "goal": {"moves": ["Qxa4"]},
         "wrong": {"Qxd7+": "The pawn is defended by the black king, so you'd lose your queen "
                            "(9) for a pawn (1)."},
         "ok": "A free rook: five points, and nothing can take your queen back."},
    ]},
    {"id": "opening-principles", "section": "Strategy", "title": "Centre and development", "steps": [
        {"fen": START, "show": ["d4", "e4", "d5", "e5"],
         "text": "The four middle squares are the most important on the board: pieces in the "
                 "centre control more squares and can quickly go either way. Start by moving a "
                 "centre pawn two squares.",
         "goal": {"moves": ["e4", "d4"]}, "hint": "Try e2 to e4, or d2 to d4."},
        {"text": "Black wants the centre too. Play Black's pawn from e7 to e5 (or d7 to d5).",
         "goal": {"moves": ["e5", "d5"]}},
        {"text": "Now bring out a knight towards the centre. Knights are happiest on f3 and c3.",
         "goal": {"moves": ["Nf3", "Nc3"]},
         "wrong": {"Nh3": "A knight on the rim is dim: on the edge it controls only half as many "
                          "squares.",
                   "Na3": "A knight on the rim is dim: on the edge it controls only half as many "
                          "squares."},
         "ok": "Good: the knight now eyes the centre."},
        {"text": "Black develops a knight too: b8 to c6 or g8 to f6.",
         "goal": {"moves": ["Nc6", "Nf6"]}},
        {"text": "Bring out a bishop next, to a square where it has open diagonals, such as c4, "
                 "b5, e2 or d3.",
         "goal": {"piece": "B"},
         "hint": "Move a bishop off the back rank, onto an open diagonal."},
        {"text": "Rules of thumb for the opening: fight for the centre, bring out your knights "
                 "and bishops before the queen, don't move the same piece twice without a good "
                 "reason, and castle early."},
    ]},
    {"id": "king-safety", "section": "Strategy", "title": "Castle early", "steps": [
        {"fen": "r1bqk1nr/pppp1ppp/2n5/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4",
         "show": ["e1", "g1"],
         "text": "A king in the middle gets attacked once the centre opens up. White's knight "
                 "and bishop have left the back rank, so the way is clear. Castle king side now.",
         "goal": {"moves": ["O-O"]},
         "ok": "Castled: the king is safe behind its pawns and the rook joins the game."},
    ]},
    {"id": "hanging", "section": "Strategy", "title": "Don't leave pieces hanging", "steps": [
        {"fen": "4k3/b7/8/3p4/4N3/8/8/4K3 w - - 0 1", "show": ["d5", "e4"],
         "text": "A piece is hanging when it can be taken for free. The black pawn on d5 is "
                 "attacking your knight. Move the knight to a safe square, and watch out for "
                 "the bishop on a7.",
         "goal": {"safe": "e4"}, "hint": "Move the knight: it's the piece in danger."},
        {"fen": "4k3/8/8/8/1b6/8/8/1R2K3 w - - 0 1", "show": ["b4"],
         "text": "Always check whether your opponent has left something hanging. Black's bishop "
                 "on b4 is giving check, but nothing defends it. Take it.",
         "goal": {"moves": ["Rxb4"]}},
    ]},

    # ---- tactics ---------------------------------------------------------------
    {"id": "forks", "section": "Tactics", "title": "Forks", "steps": [
        {"fen": "r3k3/8/8/1N6/8/8/8/4K3 w - - 0 1",
         "text": "A fork is one piece attacking two at once: your opponent can only save one of "
                 "them. Find the knight move that attacks both the king and the rook.",
         "goal": {"moves": ["Nc7+"]}, "ok": "Check, and the rook falls next move."},
        {"fen": "8/8/8/2n1b3/8/3PP3/8/K6k w - - 0 1",
         "text": "Even a pawn can fork. Find the pawn move that attacks the knight and the "
                 "bishop together.",
         "goal": {"moves": ["d4"]},
         "ok": "Whichever piece runs, you take the other. And if the bishop takes your pawn, "
               "the e3 pawn takes back."},
        {"fen": "4k3/8/8/r7/7Q/8/8/7K w - - 0 1",
         "text": "The queen is a great forking piece. Find a check that also attacks the rook.",
         "goal": {"moves": ["Qe1+"]}, "hint": "Look for a square on the e-file that also lines "
                                              "up diagonally with a5."},
    ]},
    {"id": "pins", "section": "Tactics", "title": "Pins", "steps": [
        {"fen": "4k3/8/2n5/8/8/8/8/3BK3 w - - 0 1",
         "text": "A pin is when a piece can't move because a more valuable piece is behind it. "
                 "If the piece behind is the king, moving away is against the rules. Pin the "
                 "black knight to its king.",
         "goal": {"moves": ["Ba4"]}, "hint": "Line your bishop up with the knight and the king.",
         "ok": "The knight is stuck: moving it would expose the king to check."},
    ]},
    {"id": "mates", "section": "Tactics", "title": "Checkmate patterns", "steps": [
        {"fen": "6k1/5ppp/8/8/8/8/5PPP/3Q2K1 w - - 0 1",
         "text": "The back-rank mate: a king behind its own pawns has no escape square. Find "
                 "checkmate.",
         "goal": {"mate": True}},
        {"fen": "r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4",
         "text": "The f7 square is only defended by the black king at the start. Here Black has "
                 "just played knight to f6, a blunder. Find checkmate.",
         "goal": {"mate": True}, "ok": "That's Scholar's Mate, the four-move checkmate."},
        {"fen": "k7/8/1K6/8/8/8/8/7Q w - - 0 1",
         "text": "With a king and queen you can force checkmate against a lone king. Your king "
                 "is already helping. Find checkmate.",
         "goal": {"mate": True}},
    ]},

    # ---- openings ------------------------------------------------------------------
    _opening("italian", "Italian Game",
             "The Italian Game is one of the oldest openings. White develops quickly and aims "
             "a bishop at f7, the weakest square in Black's camp. You play both sides.",
             [("e4", "White grabs the centre: pawn to e4."),
              ("e5", "Black does the same: pawn to e5."),
              ("Nf3", "White develops a knight and attacks the e5 pawn: knight to f3."),
              ("Nc6", "Black defends the pawn and develops: knight to c6."),
              ("Bc4", "White's bishop goes to c4, aiming at f7."),
              ("Bc5", "Black mirrors it: bishop to c5. This is the Giuoco Piano, the 'quiet "
                      "game'.")],
             "Both sides usually castle next, and White prepares c3 and d4 to take over the "
             "centre."),
    _opening("queens-gambit", "Queen's Gambit",
             "The Queen's Gambit starts with the queen's pawn. White offers a pawn to tempt "
             "Black's d-pawn away from the centre. You play both sides.",
             [("d4", "White plays pawn to d4."),
              ("d5", "Black answers with pawn to d5."),
              ("c4", "The gambit: pawn to c4. If Black takes it, Black gives up the centre."),
              ("e6", "The most solid answer is to decline: pawn to e6 keeps d5 supported. This "
                     "is the Queen's Gambit Declined."),
              ("Nc3", "White develops and puts more pressure on d5: knight to c3."),
              ("Nf6", "Black defends d5 again: knight to f6.")],
             "If Black had taken with pawn takes c4 (the Queen's Gambit Accepted), White plays "
             "e3 or e4 and wins the pawn back later with the bishop. That's why it's a gambit "
             "in name only."),
    _opening("ruy-lopez", "Ruy Lopez",
             "The Ruy Lopez, or Spanish Game, is a favourite of world champions. White puts "
             "pressure on the knight that defends e5. You play both sides.",
             [("e4", "Pawn to e4."),
              ("e5", "Pawn to e5."),
              ("Nf3", "Knight to f3, attacking e5."),
              ("Nc6", "Knight to c6, defending it."),
              ("Bb5", "Bishop to b5: the Ruy Lopez. The bishop attacks the knight that "
                      "defends e5."),
              ("a6", "Black asks the bishop what it wants: pawn to a6."),
              ("Ba4", "White keeps the pin going: bishop back to a4."),
              ("Nf6", "Black develops and attacks e4: knight to f6."),
              ("O-O", "White castles; e4 is safe for now because of tactics against e5.")],
             "This is the main line of the Ruy Lopez. Games from here are long, rich fights."),
    _opening("sicilian", "Sicilian Defence",
             "Against e4, the Sicilian Defence is Black's most popular and most combative "
             "reply. Black fights for the centre from the side. You play both sides.",
             [("e4", "Pawn to e4."),
              ("c5", "Pawn to c5: the Sicilian. Black controls d4 without mirroring White."),
              ("Nf3", "Knight to f3, preparing d4."),
              ("d6", "Pawn to d6, supporting a later knight on f6 and e5."),
              ("d4", "White opens the centre: pawn to d4."),
              ("cxd4", "Black trades a side pawn for White's centre pawn: c5 takes d4."),
              ("Nxd4", "White takes back with the knight."),
              ("Nf6", "Knight to f6, attacking e4."),
              ("Nc3", "Knight to c3, defending it.")],
             "This is the Open Sicilian. White usually attacks on the king side and Black "
             "counter-attacks on the queen side."),
    _opening("french", "French Defence",
             "The French Defence is a solid reply to e4. Black builds a strong pawn chain and "
             "attacks White's centre later. You play both sides.",
             [("e4", "Pawn to e4."),
              ("e6", "Pawn to e6: the French, preparing d5."),
              ("d4", "White takes the whole centre: pawn to d4."),
              ("d5", "Black strikes back at e4: pawn to d5."),
              ("e5", "White pushes past: pawn to e5. This is the Advance Variation.")],
             "Black will attack White's pawn chain at its base with c5 and f6. The bishop on "
             "c8 is hemmed in behind the e6 pawn, which is the French's one weakness."),
    _opening("london", "London System",
             "The London System is a set-up White can play against almost anything: easy to "
             "learn and hard to beat. You play both sides.",
             [("d4", "Pawn to d4."),
              ("d5", "Pawn to d5."),
              ("Bf4", "Bishop to f4 first, before e3 shuts it in."),
              ("Nf6", "Knight to f6."),
              ("e3", "Pawn to e3, opening a path for the other bishop."),
              ("e6", "Pawn to e6."),
              ("Nf3", "Knight to f3."),
              ("c5", "Black challenges the centre: pawn to c5."),
              ("c3", "White keeps d4 solid with pawn to c3.")],
             "White follows up with Bd3, Nbd2 and castling, almost whatever Black does."),
    _opening("scholars-defence", "Stopping Scholar's Mate",
             "Beginners often try Scholar's Mate: an early queen and bishop attack on f7. Here's "
             "how to stop it. You play both sides.",
             [("e4", "Pawn to e4."),
              ("e5", "Pawn to e5."),
              ("Qh5", "White brings the queen out early: queen to h5. It attacks e5 and eyes f7."),
              ("Nc6", "Black defends e5: knight to c6."),
              ("Bc4", "Bishop to c4: now queen takes f7 would be checkmate."),
              ("g6", "Black blocks the queen: pawn to g6. Don't play knight to f6 here, that "
                     "allows queen takes f7, checkmate."),
              ("Qf3", "The queen retreats but still eyes f7: queen to f3."),
              ("Nf6", "Now knight to f6 is safe and blocks the queen for good.")],
             "Black has defended and is ready to develop, while White's queen came out too "
             "early and will be chased around. Early queen attacks rarely work against careful "
             "defence."),
]

BY_ID = {lesson["id"]: lesson for lesson in LESSONS}


def catalogue():
    """The lesson list for the page."""
    return [{"id": l["id"], "section": l["section"], "title": l["title"],
             "steps": len(l["steps"])} for l in LESSONS]


def _parse(board, text):
    """SAN or UCI -> legal move in this position, or None."""
    for parse in (board.parse_san, board.parse_uci):
        try:
            return parse(text)
        except ValueError:
            pass
    return None


def _goal_moves(board, goal):
    """Every legal move that meets the goal."""
    if "moves" in goal:
        return [m for m in (_parse(board, t) for t in goal["moves"]) if m]
    out = []
    for m in board.legal_moves:
        if "from" in goal and m.from_square != chess.parse_square(goal["from"]):
            continue
        if "piece" in goal and board.piece_type_at(m.from_square) != \
                chess.Piece.from_symbol(goal["piece"]).piece_type:
            continue
        if "safe" in goal and m.from_square != chess.parse_square(goal["safe"]):
            continue
        b = board.copy(stack=False)
        b.push(m)
        if goal.get("mate") and not b.is_checkmate():
            continue
        if goal.get("check") and not b.is_check():
            continue
        if "safe" in goal and any(c.to_square == m.to_square or g >= 2
                                  for g, c in _free_captures(b)):
            continue
        out.append(m)
    return out


def _side_for(board, goal):
    """Which colour has to move to meet the goal (for steps that carry on
    from the previous position, where the right side may not be to move)."""
    square = goal.get("from") or goal.get("safe")
    if square:
        piece = board.piece_at(chess.parse_square(square))
        return piece.color if piece else board.turn
    if "moves" in goal:
        for colour in (board.turn, not board.turn):
            b = board.copy(stack=False)
            b.turn = colour
            if all(_parse(b, t) for t in goal["moves"][:1]):
                return colour
    return board.turn


class Runner:
    """Steps through one lesson. Safe to call from any thread."""

    def __init__(self):
        self.lock = threading.RLock()
        self.lesson = None
        self.i = 0
        self.board = chess.Board(EMPTY)
        self.last_move = None
        self.feedback = ""
        self.finished = False
        self.on_board = False           # use the real board (the camera reads the moves)

    # ---- moving around -------------------------------------------------------

    def open(self, lesson_id):
        with self.lock:
            self.lesson = BY_ID[lesson_id]
            self.finished = False
            self.feedback = ""
            self._enter(0, self.board)

    def go(self, i):
        """Jump to step i (Back/Next/Restart). Positions that carry on from an
        earlier step are rebuilt by playing the earlier steps' first answers."""
        with self.lock:
            if not self.lesson:
                return
            i = max(0, min(i, len(self.lesson["steps"]) - 1))
            self.finished = False
            self.feedback = ""
            board = chess.Board(EMPTY)
            for k in range(i + 1):
                self._enter(k, board)
                if k < i and self.step.get("goal"):
                    board = self.board.copy(stack=False)
                    board.push(_goal_moves(self.board, self.step["goal"])[0])
                else:
                    board = self.board

    def next(self):
        with self.lock:
            if self.lesson and self.i + 1 < len(self.lesson["steps"]):
                self.feedback = ""
                self._enter(self.i + 1, self.board)
            elif self.lesson:
                self.finished = True

    def _enter(self, i, previous):
        self.i = i
        step = self.step
        board = chess.Board(step["fen"]) if "fen" in step else previous.copy(stack=False)
        if step.get("goal"):
            board.turn = _side_for(board, step["goal"])
        board.clear_stack()
        self.board = board
        self.last_move = None if "fen" in step else self.last_move

    @property
    def step(self):
        return self.lesson["steps"][self.i]

    @property
    def wants_move(self):
        return bool(self.lesson and self.step.get("goal") and not self.finished)

    # ---- moves -------------------------------------------------------------

    def try_move(self, move):
        """Check a move (chess.Move or UCI text). Returns (correct, message)."""
        with self.lock:
            if not self.wants_move:
                return False, "Read the step, then press Next."
            board = self.board
            if isinstance(move, str):
                move = self._from_click(move)
            if move is None or move not in board.legal_moves:
                return False, self._illegal(move)
            goal = self.step["goal"]
            if move in _goal_moves(board, goal):
                message = self._praise(move)
                after = board.copy(stack=False)
                after.push(move)
                self.last_move = move
                if self.i + 1 < len(self.lesson["steps"]):
                    self._enter(self.i + 1, after)
                else:
                    self.board = after
                    self.finished = True
                self.feedback = message
                return True, message
            message = self._why_not(move)
            self.feedback = message
            return False, message

    def _from_click(self, uci):
        """A move clicked on the page; a pawn reaching the end becomes a queen."""
        try:
            move = chess.Move.from_uci(uci)
        except ValueError:
            return None
        piece = self.board.piece_at(move.from_square)
        if piece and piece.piece_type == chess.PAWN and not move.promotion \
                and chess.square_rank(move.to_square) in (0, 7):
            move.promotion = chess.QUEEN
        return move

    def _illegal(self, move):
        board = self.board
        if move is None or not board.piece_at(move.from_square):
            return "Pick up one of your pieces first."
        piece = board.piece_at(move.from_square)
        if piece.color != board.turn:
            return f"It's {'White' if board.turn else 'Black'}'s move in this step."
        if move in board.pseudo_legal_moves:
            return "You can't do that: it would leave your king in check."
        return f"A {chess.piece_name(piece.piece_type)} can't move like that."

    def _praise(self, move):
        if self.step.get("ok"):
            return "Correct! " + self.step["ok"]
        why = [r.text for r in reasons_for(self.board, move) if r.weight >= 8]
        return "Correct!" + (f" {why[0][0].upper()}{why[0][1:]}." if why else "")

    def _why_not(self, move):
        step = self.step
        for text, why in step.get("wrong", {}).items():
            if _parse(self.board, text) == move:
                return "Not quite. " + why
        if "safe" in step.get("goal", {}) and move.from_square == chess.parse_square(step["goal"]["safe"]):
            after = self.board.copy(stack=False)
            after.push(move)
            for _, c in _free_captures(after):
                if c.to_square == move.to_square:
                    name = chess.piece_name(after.piece_type_at(move.to_square))
                    by = chess.piece_name(after.piece_type_at(c.from_square))
                    return (f"Not quite. On {chess.square_name(move.to_square)} your {name} can "
                            f"still be taken by the {by} on {chess.square_name(c.from_square)}.")
        problems = problems_with(self.board, move)
        if problems:
            return "Not quite. " + problems[0].text
        return "Not quite. " + step.get("hint", "Read the step again, or press Show me.")

    def answer(self):
        """A correct move for this step, for the Show me button."""
        with self.lock:
            if not self.wants_move:
                return None
            moves = _goal_moves(self.board, self.step["goal"])
            return moves[0] if moves else None

    # ---- for the page ------------------------------------------------------------

    def highlights(self):
        out = []
        for item in self.step.get("show", []):
            if item.startswith("moves:"):
                sq = chess.parse_square(item[6:])
                b = self.board.copy(stack=False)
                piece = b.piece_at(sq)
                if piece:
                    b.turn = piece.color
                    out += [chess.square_name(m.to_square) for m in b.legal_moves
                            if m.from_square == sq]
            else:
                out.append(item)
        return sorted(set(out))

    def state(self):
        with self.lock:
            if not self.lesson:
                return {"id": None}
            return {
                "id": self.lesson["id"],
                "title": self.lesson["title"],
                "section": self.lesson["section"],
                "step": self.i,
                "steps": len(self.lesson["steps"]),
                "text": self.step["text"],
                "fen": self.board.fen(),
                "turn": "white" if self.board.turn else "black",
                "wants_move": self.wants_move,
                "show": self.highlights(),
                "last_move": self.last_move.uci() if self.last_move else None,
                "feedback": self.feedback,
                "finished": self.finished,
                "on_board": self.on_board,
            }
