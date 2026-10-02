"""Build PrusaSlicer project files (.3mf) for the chess coins.

Each coin is one object with two parts (body + symbol inlay) already
assigned to MMU filament slots:
  slot 1 = white/cream body   slot 2 = red symbols   (white set)
  slot 3 = black body         slot 4 = yellow symbols (black set)

  python3 build_3mf.py   # after exporting stl/ from coins.scad
"""
import zipfile

import numpy as np
import trimesh

SET = ["king", "queen"] + ["rook", "bishop", "knight"] * 2 + ["pawn"] * 8
BED_CENTRE = (125, 110)       # Prusa Core One bed is 250 x 220 mm
PITCH = 22                    # mm between coin centres
SLOTS = {"white": (1, 2), "black": (3, 4)}


def mesh_xml(parts):
    verts, tris, ranges, offset = [], [], [], 0
    for m in parts:
        start = sum(len(t) for t in tris)
        verts.append(m.vertices)
        tris.append(m.faces + offset)
        offset += len(m.vertices)
        ranges.append((start, start + len(m.faces) - 1))
    v = np.vstack(verts)
    t = np.vstack(tris)
    vx = "".join(f'<vertex x="{a:.5f}" y="{b:.5f}" z="{c:.5f}"/>' for a, b, c in v)
    tx = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in t)
    return f"<mesh><vertices>{vx}</vertices><triangles>{tx}</triangles></mesh>", ranges


def build(path, coins):
    """coins: list of (colour, piece)."""
    cols = int(np.ceil(np.sqrt(len(coins))))
    rows = int(np.ceil(len(coins) / cols))
    objects, items, config = [], [], []
    for i, (colour, piece) in enumerate(coins, start=1):
        body = trimesh.load(f"stl/{piece}_body.stl")
        inlay = trimesh.load(f"stl/{piece}_inlay.stl")
        xml, ranges = mesh_xml([body, inlay])
        objects.append(f'<object id="{i}" type="model">{xml}</object>')
        r, c = divmod(i - 1, cols)
        x = BED_CENTRE[0] + (c - (cols - 1) / 2) * PITCH
        y = BED_CENTRE[1] + ((rows - 1) / 2 - r) * PITCH
        items.append(f'<item objectid="{i}" transform="1 0 0 0 1 0 0 0 1 {x:.3f} {y:.3f} 0" printable="1"/>')
        body_slot, symbol_slot = SLOTS[colour]
        vols = ""
        for (first, last), name, slot in zip(ranges, ("body", "symbol"), (body_slot, symbol_slot)):
            vols += (f'<volume firstid="{first}" lastid="{last}">'
                     f'<metadata type="volume" key="name" value="{name}"/>'
                     f'<metadata type="volume" key="volume_type" value="ModelPart"/>'
                     f'<metadata type="volume" key="extruder" value="{slot}"/>'
                     f'</volume>')
        config.append(f'<object id="{i}" instances_count="1">'
                      f'<metadata type="object" key="name" value="{colour} {piece}"/>'
                      f'<metadata type="object" key="extruder" value="{body_slot}"/>{vols}</object>')

    model = ('<?xml version="1.0" encoding="UTF-8"?>\n'
             '<model unit="millimeter" xml:lang="en-US" '
             'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
             'xmlns:slic3rpe="http://schemas.slic3r.org/3mf/2017/06">'
             '<metadata name="slic3rpe:Version3mf">1</metadata>'
             f'<resources>{"".join(objects)}</resources><build>{"".join(items)}</build></model>')
    cfg = '<?xml version="1.0" encoding="utf-8"?>\n<config>' + "".join(config) + "</config>"
    types = ('<?xml version="1.0" encoding="UTF-8"?>\n'
             '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
             '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
             '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
             '</Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Target="/3D/3dmodel.model" Id="rel-1" '
            'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", types)
        z.writestr("_rels/.rels", rels)
        z.writestr("3D/3dmodel.model", model)
        z.writestr("Metadata/Slic3r_PE_model.config", cfg)


if __name__ == "__main__":
    build("chess-coins-white.3mf", [("white", p) for p in SET])
    build("chess-coins-black.3mf", [("black", p) for p in SET])
    build("chess-coins-full-set.3mf", [(c, p) for c in ("white", "black") for p in SET])
    print("wrote chess-coins-white.3mf, chess-coins-black.3mf, chess-coins-full-set.3mf")
