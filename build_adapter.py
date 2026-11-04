"""freecadcmd script: skeleton adapter, Raspberry Pi Touch Display 2 (7") -> Adafruit Metro ESP32-P4.

    freecadcmd build_adapter.py -- [--out build]

Writes build/touch2_metro_adapter.{step,3mf,stl}, plus OBJ meshes of the adapter and a
stand-in display under build/render/ for Blender. Exits non-zero and prints CHECK FAIL if a
check fails.

Frame (mm): origin at the centre of the display's Pi boss pattern, on the boss tops.
X across the display (rear view, right), Y up the display (toward the top edge, the edge with
the FPC tab), Z out of the display's back. The adapter prints flat, Z=0 on the bed.

Display (product brief, Raspberry Pi Ltd, Nov 2024, page 4): rear plate 99.71 x 168.55, Pi
bosses d5.0 at 49 x 58 centred on the plate's width, rows 68 and 126 below the plate top,
bosses about 8.5 proud of the rear face, threaded M2.5 (8 M2.5 screws supplied).
Metro ESP32-P4 (Eagle rev A, Arduino Uno pattern): 68.58 x 53.34, 3.175 holes at
(13.97, 2.54) (15.24, 50.80) (66.04, 7.62) (66.04, 35.56) from lower-left.
"""

import math
import os
import sys

import FreeCAD as App
import MeshPart
import Part

V = App.Vector
ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = ARGS[ARGS.index("--out") + 1] if "--out" in ARGS else os.path.join(os.path.dirname(os.path.abspath(__file__)), "build")

# --- adapter parameters -------------------------------------------------------------------
FRAME_T = 3.0          # frame thickness
RAIL_W = 6.0           # rail width
PAD_R = 4.5            # pad radius around each display screw
DISPLAY_HOLE_D = 2.8   # M2.5 clearance
BOSS_R = 3.75          # insert boss outer radius
BOSS_H = 9.0           # boss top above Z=0, so the Metro sits 6 mm above the frame
INSERT_D = 3.5         # M2.5 heat set insert hole
INSERT_DEPTH = 4.5     # 4.0 insert + 0.5 relief for displaced plastic
INSERT_CHAMFER = 0.4
HEAD_R = 2.5           # M2.5 pan head (ISO 7045 dk 5.0), for the clearance check
EDGE_FILLET = 0.8      # top outside edges of the frame

# --- display (rear-view drawing coords: X right from plate left, Y down from plate top) ----
PLATE_W, PLATE_H = 99.71, 168.55
PI_COLS = (25.355, 74.355)
PI_ROWS = (68.0, 126.0)
CX, CY = sum(PI_COLS) / 2, sum(PI_ROWS) / 2
BOSS_PROUD = 8.5


def dwg(X, Y):
    """Display drawing coords -> adapter frame XY."""
    return (X - CX, CY - Y)


PI_PADS = [dwg(X, Y) for X in PI_COLS for Y in PI_ROWS]

# --- Metro --------------------------------------------------------------------------------
METRO_W, METRO_H, METRO_T = 68.58, 53.34, 1.6
METRO_HOLES = [(13.97, 2.54), (15.24, 50.80), (66.04, 7.62), (66.04, 35.56)]
METRO_HOLE_D = 3.175
HOLE_CENTRE = (40.005, 26.67)   # centre of the hole bounding box
METRO_ROT = 90.0                # USB / DC edge (board X=0) points to the display's bottom
METRO_SHIFT = (-1.5, 3.5)       # keeps every insert boss clear of the display screw heads


def metro_xy(x, y):
    """Metro board coords (Eagle, top view) -> adapter frame XY."""
    a = math.radians(METRO_ROT)
    dx, dy = x - HOLE_CENTRE[0], y - HOLE_CENTRE[1]
    return (dx * math.cos(a) - dy * math.sin(a) + METRO_SHIFT[0],
            dx * math.sin(a) + dy * math.cos(a) + METRO_SHIFT[1])


BOSSES = [metro_xy(*h) for h in METRO_HOLES]


def outline():
    """2D outline of the U frame: three rails and four pads, concave corners rounded r 1.5."""
    (lb, lt), (rb, rt) = (PI_PADS[1], PI_PADS[0]), (PI_PADS[3], PI_PADS[2])
    faces = []
    for (x0, y0), (x1, y1) in ((lb, lt), (rb, rt), (lt, rt)):
        length = math.hypot(x1 - x0, y1 - y0)
        rect = Part.makePlane(length, RAIL_W, V(0, -RAIL_W / 2, 0))
        rect.rotate(V(0, 0, 0), V(0, 0, 1), math.degrees(math.atan2(y1 - y0, x1 - x0)))
        rect.translate(V(x0, y0, 0))
        faces.append(rect)
    faces += [Part.Face(Part.Wire(Part.makeCircle(PAD_R, V(x, y, 0)))) for x, y in PI_PADS]
    face = faces[0].fuse(faces[1:]).removeSplitter()
    face = Part.Face(face.Faces[0].OuterWire) if len(face.Faces) == 1 else face
    return face.makeOffset2D(1.5).makeOffset2D(-1.5)


def adapter():
    frame = outline().extrude(V(0, 0, FRAME_T))
    frame = Part.Solid(Part.Shell(frame.Faces)) if frame.ShapeType != "Solid" else frame
    try:
        top = [e for e in frame.Edges
               if abs(e.BoundBox.ZMin - FRAME_T) < 1e-6 and abs(e.BoundBox.ZMax - FRAME_T) < 1e-6]
        filleted = frame.makeFillet(EDGE_FILLET, top)
        if filleted.isValid():
            frame = filleted
        else:
            print("fillet skipped: invalid result")
    except Exception as err:  # noqa: BLE001 - fillet is cosmetic
        print("fillet skipped: %s" % err)
    bosses = [Part.makeCylinder(BOSS_R, BOSS_H, V(x, y, 0)) for x, y in BOSSES]
    body = frame.fuse(bosses).removeSplitter()

    cuts = [Part.makeCylinder(DISPLAY_HOLE_D / 2, FRAME_T + 2, V(x, y, -1)) for x, y in PI_PADS]
    for x, y in BOSSES:
        cuts.append(Part.makeCylinder(INSERT_D / 2, INSERT_DEPTH + 1, V(x, y, BOSS_H - INSERT_DEPTH)))
        cuts.append(Part.makeCone(INSERT_D / 2, INSERT_D / 2 + INSERT_CHAMFER, INSERT_CHAMFER,
                                  V(x, y, BOSS_H - INSERT_CHAMFER)))
    return body.cut(Part.makeCompound(cuts)).removeSplitter()


def rounded_rect(w, h, r, z0, t, cx=0.0, cy=0.0):
    box = Part.makeBox(w, h, t, V(cx - w / 2, cy - h / 2, z0))
    vertical = [e for e in box.Edges if abs(e.BoundBox.XMax - e.BoundBox.XMin) < 1e-6
                and abs(e.BoundBox.YMax - e.BoundBox.YMin) < 1e-6]
    return box.makeFillet(r, vertical)


def display():
    """Stand-in Touch Display 2 7", from the product brief drawing. No official STEP exists."""
    rear = -BOSS_PROUD                    # rear face of the metal plate
    total = 14.92                         # glass front to boss tips
    glass_t = 1.8
    px0, py0 = dwg(0, 0)
    plate_c = (px0 + PLATE_W / 2, py0 - PLATE_H / 2)
    glass_c = (plate_c[0], (py0 + 6.45 + py0 - PLATE_H - 14.32) / 2)
    parts = {}
    parts["glass"] = rounded_rect(120.24, 189.32, 8.0, -total, glass_t, *glass_c)
    parts["body"] = rounded_rect(PLATE_W, PLATE_H, 1.5, -total + glass_t, total - glass_t - BOSS_PROUD, *plate_c)
    bosses = []
    for x, y in PI_PADS:
        b = Part.makeCylinder(2.5, BOSS_PROUD, V(x, y, rear)).cut(
            Part.makeCylinder(1.1, 4, V(x, y, -3.99)))
        bosses.append(b)
    for X in (14.5, 85.21):
        for Y in (18.21, 158.21):
            x, y = dwg(X, Y)
            blk = rounded_rect(13.0, 7.0, 0.6, rear, 3.0, x, y).cut(Part.makeCylinder(1.1, 4, V(x, y, rear + 0.5)))
            bosses.append(blk)
    parts["bosses"] = Part.makeCompound(bosses)
    rails = []
    for X in (31.7, 67.4):
        x, _ = dwg(X, 0)
        y0, y1 = dwg(0, 7.5)[1], dwg(0, 128)[1]
        rails.append(Part.makeBox(1.6, y0 - y1, 1.2, V(x - 0.8, y1, rear)))
    xa, ya = dwg(31.7, 7.5)
    xb, _ = dwg(67.4, 7.5)
    rails.append(Part.makeBox(xb - xa, 1.6, 1.2, V(xa, ya - 0.8, rear)))
    parts["rails"] = Part.makeCompound(rails)
    fx0, fy0 = dwg(39.0, 101.6)
    fx1, fy1 = dwg(61.0, 108.4)
    parts["fpc"] = Part.makeBox(fx1 - fx0, fy0 - fy1, 2.0, V(fx0, fy1, rear))
    parts["latch"] = Part.makeBox(fx1 - fx0 - 1.0, 1.6, 0.6, V(fx0 + 0.5, fy1 - 0.2, rear + 2.0))
    qx0, qy0 = dwg(23.5, 85.0)
    qx1, qy1 = dwg(31.6, 96.5)
    parts["power"] = Part.makeBox(qx1 - qx0, qy0 - qy1, 4.5, V(qx0, qy1, rear))
    return parts


def write_obj(shape, path, fine=True):
    mesh = MeshPart.meshFromShape(Shape=shape, LinearDeflection=0.01 if fine else 0.05,
                                  AngularDeflection=0.08 if fine else 0.3, Relative=False)
    mesh.write(path)
    print("wrote %s, %d facets" % (path, mesh.CountFacets))


def checks(part, disp):
    ok = True

    def check(name, good, detail):
        nonlocal ok
        print("CHECK %s %s: %s" % ("ok  " if good else "FAIL", name, detail))
        ok = ok and good

    check("valid solid", part.isValid() and len(part.Solids) == 1, "%d solid(s)" % len(part.Solids))
    # Boss centres against the Metro holes, by an independent transform (rotate 90: x,y -> -y,x)
    for (hx, hy), (bx, by) in zip(METRO_HOLES, BOSSES):
        ex = -(hy - HOLE_CENTRE[1]) + METRO_SHIFT[0]
        ey = (hx - HOLE_CENTRE[0]) + METRO_SHIFT[1]
        check("boss on Metro hole (%.2f, %.2f)" % (hx, hy), math.hypot(ex - bx, ey - by) < 1e-6,
              "(%.3f, %.3f)" % (bx, by))
    # Uno pattern spacing survives the transform
    d = [math.hypot(BOSSES[i][0] - BOSSES[j][0], BOSSES[i][1] - BOSSES[j][1]) for i in range(4) for j in range(i + 1, 4)]
    e = [math.hypot(METRO_HOLES[i][0] - METRO_HOLES[j][0], METRO_HOLES[i][1] - METRO_HOLES[j][1]) for i in range(4) for j in range(i + 1, 4)]
    check("hole spacing preserved", max(abs(a - b) for a, b in zip(d, e)) < 1e-6, "max err %.1e" % max(abs(a - b) for a, b in zip(d, e)))
    gap = min(math.hypot(bx - px, by - py) - BOSS_R - HEAD_R for bx, by in BOSSES for px, py in PI_PADS)
    check("boss clear of display screw heads", gap >= 0.3, "%.2f mm" % gap)
    check("Pi pattern 49 x 58", abs(PI_PADS[2][0] - PI_PADS[0][0] - 49) < 1e-6 and abs(PI_PADS[0][1] - PI_PADS[1][1] - 58) < 1e-6, str(PI_PADS))
    floor = BOSS_H - INSERT_DEPTH
    check("insert floor", floor >= 1.5, "%.1f mm under the insert" % floor)
    wall = BOSS_R - INSERT_D / 2
    check("boss wall", wall >= 1.6, "%.2f mm" % wall)
    clear = BOSS_H - FRAME_T
    check("Metro underside above frame", clear >= 4.0, "%.1f mm (through-hole pins about 2)" % clear)
    # Metro outline within the display's rear plate
    corners = [metro_xy(x, y) for x in (0, METRO_W) for y in (0, METRO_H)]
    px0, py0 = dwg(0, 0)
    inside = all(px0 + 3 < x < px0 + PLATE_W - 3 and py0 - PLATE_H + 3 < y < py0 - 3 for x, y in corners)
    check("Metro inside rear plate", inside, "x %.1f..%.1f y %.1f..%.1f" % (
        min(c[0] for c in corners), max(c[0] for c in corners), min(c[1] for c in corners), max(c[1] for c in corners)))
    # Adapter against the display stand-in: only the boss tops may touch (Z=0 contact)
    hit = sum(part.common(s).Volume for s in disp.values())
    check("adapter clear of display", hit < 1e-3, "overlap %.4f mm3" % hit)
    # Ribbon gap: no adapter material over the FPC connector
    fpc = disp["fpc"].BoundBox
    over = Part.makeBox(fpc.XLength, fpc.YLength, 20, V(fpc.XMin, fpc.YMin, -1))
    check("open over DSI connector", part.common(over).Volume < 1e-3, "y %.1f..%.1f" % (fpc.YMin, fpc.YMax))
    bb = part.BoundBox
    print("adapter %.1f x %.1f x %.1f mm, %.2f cm3" % (bb.XLength, bb.YLength, bb.ZLength, part.Volume / 1000))
    return ok


def main():
    os.makedirs(os.path.join(OUT, "render"), exist_ok=True)
    part = adapter()
    disp = display()
    ok = checks(part, disp)
    base = os.path.join(OUT, "touch2_metro_adapter")
    part.exportStep(base + ".step")
    doc = App.newDocument("touch2_metro_adapter")
    doc.addObject("Part::Feature", "Adapter").Shape = part
    doc.recompute()
    doc.saveAs(base + ".FCStd")
    for ext in (".3mf", ".stl"):
        MeshPart.meshFromShape(Shape=part, LinearDeflection=0.02, AngularDeflection=0.15,
                               Relative=False).write(base + ext)
    write_obj(part, os.path.join(OUT, "render", "adapter.obj"))
    for name, shape in disp.items():
        write_obj(shape, os.path.join(OUT, "render", "display_%s.obj" % name))
    with open(os.path.join(OUT, "render", "layout.txt"), "w") as f:
        f.write("bosses %s\npads %s\nboss_h %s\nframe_t %s\nmetro_rot %s\nhole_centre %s\nshift %s\n" % (
            BOSSES, PI_PADS, BOSS_H, FRAME_T, METRO_ROT, HOLE_CENTRE, METRO_SHIFT))
    print("ALL CHECKS PASS" if ok else "CHECK FAIL")
    sys.stdout.flush()
    os._exit(0 if ok else 1)


main()
