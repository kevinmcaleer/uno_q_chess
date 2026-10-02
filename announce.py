"""How the human finds out what the computer played."""
import shutil
import subprocess

import chess
import cv2

from vision import SQ

PIECE_NAMES = {chess.PAWN: "pawn", chess.KNIGHT: "knight", chess.BISHOP: "bishop",
               chess.ROOK: "rook", chess.QUEEN: "queen", chess.KING: "king"}


def describe(board, move):
    """Plain-English description, e.g. 'knight from g8 to f6, taking the pawn'.
    `board` is the position *before* the move."""
    if board.is_castling(move):
        side = "king side" if chess.square_file(move.to_square) == 6 else "queen side"
        return f"castle {side}: king {chess.square_name(move.from_square)} to " \
               f"{chess.square_name(move.to_square)} and move the rook"
    piece = PIECE_NAMES[board.piece_type_at(move.from_square)]
    text = f"{piece} from {chess.square_name(move.from_square)} to {chess.square_name(move.to_square)}"
    if board.is_en_passant(move):
        text += ", taking the pawn en passant"
    elif board.is_capture(move):
        text += f", taking the {PIECE_NAMES[board.piece_type_at(move.to_square)]}"
    if move.promotion:
        text += f", and promote to a {PIECE_NAMES[move.promotion]}"
    return text


def say(text):
    print(f">>> {text}", flush=True)
    for tts in ("espeak-ng", "espeak"):
        if shutil.which(tts):
            subprocess.Popen([tts, text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            break


def centre(square):
    f, r = chess.square_file(square), chess.square_rank(square)
    return int((f + 0.5) * SQ), int((7 - r + 0.5) * SQ)


def draw_move(board_img, move, path="last_move.png", show=False):
    """Draw an arrow for the move on the straightened board image."""
    img = board_img.copy()
    cv2.arrowedLine(img, centre(move.from_square), centre(move.to_square),
                    (0, 0, 255), 12, tipLength=0.25)
    cv2.imwrite(path, img)
    if show:
        cv2.imshow("chess", img)
        cv2.waitKey(1)
