// Camera-friendly chess pieces for the chess camera project.
//
// Low, wide pieces with a flat top and a raised symbol, so a camera looking
// down can see them clearly and they don't lean into neighbouring squares.
//
// Set `square` to your board's square size (mm), then export each piece.
// part = "all"    : body + symbol in one STL (swap filament at the symbol
//                   layer, or paint the symbol)
// part = "body"   : just the body   } load both into a multi-colour slicer
// part = "symbol" : just the symbol } (AMS / MMU) as one object
//
// Print upright, no supports, 0.2 mm layers, 3 walls, 15% infill.

piece  = "king";      // king, queen, rook, bishop, knight, pawn
part   = "all";       // all, body, symbol
square = 50;          // board square size in mm (measure yours)

relief      = 1.2;    // symbol height above the top face
base_r      = square * 0.36;   // footprint 72% of the square
top_r       = square * 0.33;   // flat top 66% of the square
pawn_top_r  = square * 0.30;
recess_d    = 0;      // e.g. 20 for a coin or washer weight under the base (0 = none)
recess_h    = 3;

$fn = 96;

heights = [["pawn", 14], ["rook", 18], ["knight", 18],
           ["bishop", 20], ["queen", 23], ["king", 25]];
function height(p) = heights[search([p], heights)[0]][1];
function tr(p) = p == "pawn" ? pawn_top_r : top_r;

// Outline (radius, z) of a turned piece: foot, waist, then a 45-degree
// flare up to the flat top so it prints without supports.
module profile(H, waist_r, t_r) {
    flare_start = H - 2 - (t_r - waist_r);
    polygon([[0, 0], [base_r - 0.6, 0], [base_r, 0.6], [base_r, 3],
             [waist_r, 3 + (base_r - waist_r) * 0.5],
             [waist_r, flare_start], [t_r, H - 2], [t_r, H], [0, H]]);
}

// Diamond-section ring around the waist (45-degree faces, prints cleanly).
module ring(z, r, sides) {
    rotate_extrude($fn = sides) translate([r, z]) rotate(45) square(2.2, center = true);
}

module body(p) {
    H = height(p);
    sides = p == "knight" ? 8 : $fn;    // the knight is octagonal, easy to feel
    waist = p == "rook" ? top_r - 2 : p == "pawn" ? square * 0.2 : square * 0.18;
    difference() {
        union() {
            rotate_extrude($fn = sides) profile(H, waist, tr(p));
            if (p == "bishop") ring(H * 0.5, waist, sides);
            if (p == "queen")  { ring(H * 0.42, waist, sides); ring(H * 0.58, waist, sides); }
            if (p == "king")   { ring(H * 0.38, waist, sides); ring(H * 0.5, waist, sides);
                                 ring(H * 0.62, waist, sides); }
        }
        if (recess_d > 0) translate([0, 0, -0.01]) cylinder(d = recess_d, h = recess_h);
    }
}

// 2D symbols, sized to fit the top face.
module symbol2d(p) {
    s = tr(p) * 2 * 0.72;            // symbol fits in 72% of the top
    w = s * 0.2;                     // stroke width
    if (p == "king")                 // plus sign
        union() { square([s, w], center = true); square([w, s], center = true); }
    if (p == "queen")                // crown of five dots around a centre dot
        union() {
            circle(d = w * 1.1);
            for (a = [0 : 72 : 359]) rotate(a + 90) translate([s * 0.38, 0]) circle(d = w * 1.1);
        }
    if (p == "rook")                 // square outline
        difference() { square(s * 0.85, center = true); square(s * 0.85 - 2 * w, center = true); }
    if (p == "bishop")               // diagonal slash
        rotate(45) square([s * 1.05, w], center = true);
    if (p == "knight")               // letter L
        translate([-s * 0.3, -s * 0.4]) union() { square([w, s * 0.8]); square([s * 0.6, w]); }
    if (p == "pawn")                 // single dot
        circle(d = s * 0.45);
}

module symbol(p) {
    translate([0, 0, height(p)]) linear_extrude(relief) symbol2d(p);
}

if (part == "all" || part == "body")   body(piece);
if (part == "all" || part == "symbol") symbol(piece);
