"""Generate a printable, true-size chessboard tiled across A4 or Letter sheets.

  python3 make_board.py            # writes chessboard-A4.pdf and chessboard-Letter.pdf
  python3 make_board.py --square 45

Squares default to 50 mm to match the printed pieces in ../pieces.
"""
import argparse

from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

LIGHT = HexColor("#C9D3E0")   # pale blue-grey: contrasts with black pieces
DARK = HexColor("#5F7FA8")    # mid blue: contrasts with cream pieces
GREY = HexColor("#888888")
BORDER = 15                   # mm of labelled border around the squares
MARGIN = 10                   # mm white margin on each sheet
OVERLAP = 10                  # mm of pattern repeated on the next sheet for gluing


def draw_poster(c, sq):
    """Draw the whole board in poster coordinates (mm, origin top-left, y down)."""
    board = 8 * sq
    for f in range(8):
        for r in range(8):
            x, y = BORDER + f * sq, BORDER + (7 - r) * sq
            c.setFillColor(LIGHT if (f + r) % 2 else DARK)     # a1 is dark
            c.rect(x * mm, -(y + sq) * mm, sq * mm, sq * mm, stroke=0, fill=1)
    c.setStrokeColor(black)
    c.setLineWidth(2 * mm)
    c.rect((BORDER - 1) * mm, -(BORDER + board + 1) * mm, (board + 2) * mm, (board + 2) * mm,
           stroke=1, fill=0)
    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 16)
    for i in range(8):
        cx = BORDER + (i + 0.5) * sq
        for y in (BORDER / 2 + 2.5, BORDER + board + BORDER / 2 + 2.5):
            c.drawCentredString(cx * mm, -y * mm, "abcdefgh"[i])
        cy = BORDER + (7 - i + 0.5) * sq + 2.5
        for x in (BORDER / 2, BORDER + board + BORDER / 2):
            c.drawCentredString(x * mm, -cy * mm, str(i + 1))


def scale_bar(c, x, y, length=50):
    c.setStrokeColor(black)
    c.setLineWidth(0.4)
    c.line(x * mm, y * mm, (x + length) * mm, y * mm)
    for t in (x, x + length):
        c.line(t * mm, (y - 1.5) * mm, t * mm, (y + 1.5) * mm)
    c.setFont("Helvetica", 7)
    c.setFillColor(black)
    c.drawString((x + length + 2) * mm, (y - 1) * mm, f"should measure {length} mm")


def make(path, pagesize, sq, paper_name):
    pw, ph = pagesize[0] / mm, pagesize[1] / mm
    cw, ch = pw - 2 * MARGIN, ph - 2 * MARGIN - 10      # leave room for the sheet label
    step_x, step_y = cw - OVERLAP, ch - OVERLAP
    total = 8 * sq + 2 * BORDER
    cols = -(-int(total - OVERLAP) // int(step_x)) if total > cw else 1
    rows = -(-int(total - OVERLAP) // int(step_y)) if total > ch else 1
    while cols * step_x + OVERLAP < total:
        cols += 1
    while rows * step_y + OVERLAP < total:
        rows += 1

    c = canvas.Canvas(path, pagesize=pagesize)
    c.setTitle(f"Chessboard, {sq} mm squares ({paper_name})")

    # Instructions page with an assembly map
    c.setFont("Helvetica-Bold", 20)
    c.drawString(MARGIN * mm, (ph - MARGIN - 10) * mm, "Printable chessboard")
    c.setFont("Helvetica", 11)
    lines = [
        f"{sq} mm squares, {8 * sq / 10:.0f} cm board, on {rows * cols} {paper_name} sheets.",
        "",
        "1. Print at 100% / 'Actual size' (turn off 'Fit to page').",
        "   Check the 50 mm bar at the bottom of each sheet with a ruler.",
        "2. Matte paper works best: shiny paper reflects light into the camera.",
        "3. Lay the sheets out as in the map below.",
        "4. On every sheet except those in the top row, cut off the top white margin",
        "   exactly along the edge of the printed area. Do the same for the left margin",
        "   on every sheet except those in the left column.",
        "5. Lay each trimmed edge over the 10 mm strip it overlaps on the neighbouring",
        "   sheet, line up the pattern, and tape or glue it from the back.",
        "6. Glue the finished board onto card or foam board to keep it flat.",
    ]
    y = ph - MARGIN - 22
    for line in lines:
        c.drawString(MARGIN * mm, y * mm, line)
        y -= 6
    # Map
    scale = min((pw - 2 * MARGIN) / (cols * step_x + OVERLAP), (y - MARGIN - 20) / (rows * step_y + OVERLAP))
    ox, oy = MARGIN, y - 8
    c.saveState()
    c.translate(ox * mm, oy * mm)
    c.scale(scale, scale)
    draw_poster(c, sq)
    c.restoreState()
    c.setStrokeColor(HexColor("#D0342C"))
    c.setLineWidth(1)
    c.setFont("Helvetica-Bold", 12)
    for r in range(rows):
        for col in range(cols):
            x0, y0 = ox + col * step_x * scale, oy - r * step_y * scale
            c.rect(x0 * mm, (y0 - ch * scale) * mm, cw * scale * mm, ch * scale * mm)
            c.setFillColor(HexColor("#D0342C"))
            c.drawString((x0 + 2) * mm, (y0 - 6) * mm, f"{'ABCDEFG'[r]}{col + 1}")
    scale_bar(c, MARGIN, MARGIN)
    c.showPage()

    # Tiles
    for r in range(rows):
        for col in range(cols):
            top = ph - MARGIN                         # page y (mm) of content top
            c.saveState()
            p = c.beginPath()
            p.rect(MARGIN * mm, (top - ch) * mm, cw * mm, ch * mm)
            c.clipPath(p, stroke=0, fill=0)
            c.translate((MARGIN - col * step_x) * mm, (top + r * step_y) * mm)
            draw_poster(c, sq)
            c.restoreState()
            # crop marks at the content corners
            c.setStrokeColor(GREY)
            c.setLineWidth(0.3)
            for x in (MARGIN, MARGIN + cw):
                for yy in (top, top - ch):
                    c.line((x - 4) * mm if x == MARGIN else (x + 1) * mm, yy * mm,
                           (x - 1) * mm if x == MARGIN else (x + 4) * mm, yy * mm)
                    c.line(x * mm, (yy + 1) * mm if yy == top else (yy - 1) * mm,
                           x * mm, (yy + 4) * mm if yy == top else (yy - 4) * mm)
            # overlap strip guides
            c.setDash(2, 2)
            if col < cols - 1:
                c.line((MARGIN + step_x) * mm, top * mm, (MARGIN + step_x) * mm, (top - ch) * mm)
            if r < rows - 1:
                c.line(MARGIN * mm, (top - step_y) * mm, (MARGIN + cw) * mm, (top - step_y) * mm)
            c.setDash()
            c.setFont("Helvetica-Bold", 10)
            c.setFillColor(black)
            label = f"Sheet {'ABCDEFG'[r]}{col + 1}"
            c.drawString(MARGIN * mm, (MARGIN + 2) * mm, label)
            c.setFont("Helvetica", 7)
            c.drawString((MARGIN + 22) * mm, (MARGIN + 2) * mm,
                         "Print at 100%. Dashed line: the next sheet overlaps up to here.")
            scale_bar(c, pw - MARGIN - 80, MARGIN + 3)
            c.showPage()
    c.save()
    return rows * cols


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--square", type=float, default=50, help="square size in mm")
    a = ap.parse_args()
    for name, size in (("A4", A4), ("Letter", letter)):
        n = make(f"chessboard-{name}.pdf", size, a.square, name)
        print(f"chessboard-{name}.pdf: {n} sheets + instructions")
