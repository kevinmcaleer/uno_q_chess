"""Tell the app where the board is in the camera image.

Run once after fixing the camera in place (and again if it moves).

  With a screen attached:   python3 calibrate.py
      Click the outer corners of a8, h8, h1, a1 in that order, then press s.

  Headless (SSH):           python3 calibrate.py --snapshot
      Saves snapshot.jpg. Open it on your computer, note the four corner
      pixel positions, then:
                            python3 calibrate.py --corners 102,40 690,38 700,630 95,640

Writes calibration.json and board_check.jpg (the straightened board with a
grid drawn on it, so you can check the squares line up).
"""
import argparse
import json

import cv2

from vision import SQ, WARP_SIZE, Camera, homography_from_corners, warp

LABELS = ["a8", "h8", "h1", "a1"]


def click_corners(img):
    pts = []

    def on_click(event, x, y, *_):
        if event == cv2.EVENT_LBUTTONDOWN and len(pts) < 4:
            pts.append((x, y))

    cv2.namedWindow("calibrate")
    cv2.setMouseCallback("calibrate", on_click)
    while True:
        view = img.copy()
        for i, p in enumerate(pts):
            cv2.circle(view, p, 6, (0, 0, 255), -1)
            cv2.putText(view, LABELS[i], (p[0] + 8, p[1] - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        hint = f"click corner of {LABELS[len(pts)]}" if len(pts) < 4 else "press s to save"
        cv2.putText(view, hint, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        cv2.imshow("calibrate", view)
        key = cv2.waitKey(30) & 0xFF
        if key == ord("s") and len(pts) == 4:
            break
        if key == ord("r"):
            pts.clear()
    cv2.destroyAllWindows()
    return pts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--snapshot", action="store_true", help="just save snapshot.jpg")
    ap.add_argument("--corners", nargs=4, metavar="X,Y",
                    help="pixel corners of a8 h8 h1 a1 (skips the click window)")
    args = ap.parse_args()

    img = Camera(args.camera).frame()
    if args.snapshot:
        cv2.imwrite("snapshot.jpg", img)
        print("Saved snapshot.jpg")
        return

    if args.corners:
        corners = [tuple(int(v) for v in c.split(",")) for c in args.corners]
    else:
        corners = click_corners(img)

    H = homography_from_corners(corners)
    with open("calibration.json", "w") as f:
        json.dump({"corners": corners, "homography": H.tolist()}, f, indent=2)

    check = warp(img, H)
    for i in range(9):
        cv2.line(check, (i * SQ, 0), (i * SQ, WARP_SIZE), (0, 255, 0), 1)
        cv2.line(check, (0, i * SQ), (WARP_SIZE, i * SQ), (0, 255, 0), 1)
    cv2.putText(check, "a8", (5, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
    cv2.imwrite("board_check.jpg", check)
    print("Saved calibration.json and board_check.jpg (a8 should be top-left)")


if __name__ == "__main__":
    main()
