"""Play chess against Stockfish on a real board watched by a webcam.

  python3 main.py                  # you play white
  python3 main.py --colour black   # computer opens
  python3 main.py --hints          # also suggest a move for you each turn

Set up the starting position, run calibrate.py once, then start this.
"""
import argparse

import chess

from announce import describe, draw_move, say
from detector import infer_move
from engine import Engine
from vision import Camera, change_scores, load_calibration


def read_move(cam, board, reference, args):
    """Wait for the board to change and settle, then work out the move.
    Returns (move, settled_image). Falls back to typing after repeated misses."""
    misses = 0
    while True:
        settled = cam.wait_for_board_change(reference, args.change_threshold)
        move, fit = infer_move(board, change_scores(reference, settled), args.min_fit)
        if move:
            return move, settled
        misses += 1
        say("I couldn't read that move. Please check the pieces are centred on their squares.")
        if misses >= 3:
            typed = input("Type the move (e.g. e2e4) or press Enter to keep watching: ").strip()
            if typed:
                try:
                    move = board.parse_uci(typed)
                    return move, cam.wait_until_still()
                except ValueError:
                    print("Not a legal move here.")
            misses = 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--colour", choices=["white", "black"], default="white",
                    help="the colour YOU play")
    ap.add_argument("--skill", type=int, default=5, help="Stockfish skill 0-20")
    ap.add_argument("--think", type=float, default=0.5, help="engine seconds per move")
    ap.add_argument("--hints", action="store_true", help="suggest a move on your turn")
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--show", action="store_true", help="show a window (needs a screen)")
    ap.add_argument("--change-threshold", type=float, default=25.0)
    ap.add_argument("--min-fit", type=float, default=10.0)
    args = ap.parse_args()

    human = chess.WHITE if args.colour == "white" else chess.BLACK
    cam = Camera(args.camera, load_calibration())
    engine = Engine(skill=args.skill, think_time=args.think)
    board = chess.Board()

    say("Set up the starting position and take your hands away.")
    reference = cam.wait_until_still()
    say("Board ready.")

    try:
        while not board.is_game_over():
            if board.turn == human:
                if args.hints:
                    say("Hint: " + describe(board, engine.suggest(board)))
                say("Your move.")
                move, reference = read_move(cam, board, reference, args)
                say("You played " + describe(board, move))
                board.push(move)
            else:
                expected = engine.play(board)
                say("I play " + describe(board, expected) + ". Please make that move for me.")
                draw_move(reference, expected, show=args.show)
                while True:
                    move, settled = read_move(cam, board, reference, args)
                    if move == expected:
                        break
                    say(f"That looks like {describe(board, move)}. "
                        f"Please put it back and play {describe(board, expected)}.")
                reference = settled
                board.push(move)
            print(board, "\n", flush=True)
            if board.is_check():
                say("Check.")
        say(f"Game over: {board.result()}")
    finally:
        engine.close()


if __name__ == "__main__":
    main()
