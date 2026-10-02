// Chess coins: flat two-colour discs for the chess camera project.
//
// Each coin is a disc with the piece symbol inlaid flush into the top, so
// the camera sees a clean, shadow-free mark and the coins stack neatly.
// Designed for multi-material printing (e.g. Prusa Core One + MMU3):
// the body and the inlay are separate parts that fit together exactly.
//
// part = "body"  : the disc with the symbol pocket cut out
// part = "inlay" : the symbol that fills the pocket
// part = "all"   : both together (single-colour print, or for previews)

piece  = "king";      // king, queen, rook, bishop, knight, pawn
part   = "all";
square = 19.5;        // board square size in mm (yours is just under 20)

diameter     = square * 0.77;  // 15 mm on a 19.5 mm square
thickness    = 4;
inlay_depth  = 1.0;            // 5 layers at 0.2 mm
chamfer      = 0.6;

$fn = 128;

module disc() {
    r = diameter / 2;
    rotate_extrude() polygon([[0, 0], [r - chamfer, 0], [r, chamfer],
                              [r, thickness - chamfer], [r - chamfer, thickness],
                              [0, thickness]]);
}

module symbol2d(p) {
    s = diameter * 0.62;
    w = s * 0.2;
    if (p == "king")
        union() { square([s, w], center = true); square([w, s], center = true); }
    if (p == "queen")
        union() {
            circle(d = w * 1.1);
            for (a = [0 : 72 : 359]) rotate(a + 90) translate([s * 0.38, 0]) circle(d = w * 1.1);
        }
    if (p == "rook")
        difference() { square(s * 0.85, center = true); square(s * 0.85 - 2 * w, center = true); }
    if (p == "bishop")
        rotate(45) square([s * 1.05, w], center = true);
    if (p == "knight")
        translate([-s * 0.3, -s * 0.4]) union() { square([w, s * 0.8]); square([s * 0.6, w]); }
    if (p == "pawn")
        circle(d = s * 0.45);
}

module inlay() {
    translate([0, 0, thickness - inlay_depth]) linear_extrude(inlay_depth) symbol2d(piece);
}

if (part == "body" || part == "all") difference() { disc(); inlay(); }
if (part == "inlay" || part == "all") inlay();
