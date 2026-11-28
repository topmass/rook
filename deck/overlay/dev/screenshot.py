"""Renders overlay/page headlessly at the Deck's 1280x800, one PNG per scene, over a bright stand-in game frame, and
checks the page keeps off the top-centre WoW data strip (1024 x 6 px) and the centre of the screen.

    uv run --no-project --with playwright --with pillow overlay/dev/screenshot.py [--browser /usr/bin/chromium-browser]

Needs overlay/dev/fake_server.py running on --port (default 47331). Writes overlay/screenshots/*.png.
"""

import argparse
import os
import random
import sys

from PIL import Image, ImageDraw, ImageFilter
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "screenshots")
W, H = 1280, 800
STRIP = (128, 0, 1152, 6)  # The WoW add-on's data strip: 1024 x 6 px, top centre.
CENTRE = (W // 3, H // 3, 2 * W // 3, 2 * H // 3)  # The middle third each way.
SCENES = ["listening", "thinking", "speaking", "answer", "waiting", "resting"]


def game_frame():
    """A bright, busy stand-in for a game: sky to meadow, a low sun at the top right, foliage noise, the strip."""
    img = Image.new("RGB", (W, H))
    px = img.load()
    for y in range(H):
        t = y / H
        sky = (int(150 + 90 * (1 - t)), int(190 + 50 * (1 - t)), 255)
        grass = (int(70 + 40 * t), int(140 - 30 * t), int(60 - 20 * t))
        k = min(1, max(0, (t - 0.45) * 4))
        row = tuple(int(sky[i] * (1 - k) + grass[i] * k) for i in range(3))
        for x in range(W):
            px[x, y] = row
    d = ImageDraw.Draw(img)
    d.ellipse((1000, 40, 1240, 280), fill=(255, 248, 220))
    rnd = random.Random(4)
    for _ in range(900):
        x, y = rnd.randrange(W), rnd.randrange(int(H * 0.45), H)
        r = rnd.randrange(3, 18)
        d.ellipse((x - r, y - r, x + r, y + r), fill=(rnd.randrange(30, 120), rnd.randrange(90, 190), rnd.randrange(20, 80)))
    for _ in range(25):
        x, y = rnd.randrange(W), rnd.randrange(60, int(H * 0.45))
        d.ellipse((x - 60, y - 18, x + 60, y + 18), fill=(250, 252, 255))
    img = img.filter(ImageFilter.GaussianBlur(1.2))
    d = ImageDraw.Draw(img)
    for i in range(512):  # The add-on's 2x2 px data squares.
        c = rnd.randrange(256), rnd.randrange(256), rnd.randrange(256)
        x = STRIP[0] + 2 * i
        d.rectangle((x, 0, x + 1, 5), fill=c)
    return img


def check(shot):
    """Every pixel of the strip and the centre is fully transparent."""
    a = shot.getchannel("A")
    strip = max(a.crop(STRIP).tobytes())
    centre = max(a.crop(CENTRE).tobytes())
    bbox = a.point(lambda v: 255 if v > 0 else 0).getbbox()
    return strip, centre, bbox


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=47331)
    p.add_argument("--browser", default="/usr/bin/chromium-browser")
    p.add_argument("--anchor", default="middle-right")
    p.add_argument("--scenes", default=",".join(SCENES))
    a = p.parse_args()
    os.makedirs(OUT, exist_ok=True)
    frame = game_frame().convert("RGBA")
    bad = False
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=a.browser, headless=True,
                                     args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
        for scene in a.scenes.split(","):
            page = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
            logs = []
            page.on("console", lambda m: logs.append(m.text))
            page.on("pageerror", lambda e: logs.append(f"pageerror: {e}"))
            page.goto(f"http://127.0.0.1:{a.port}/overlay?anchor={a.anchor}&events=/overlay/events%3Fscene%3D{scene}")
            page.wait_for_timeout(3000 if scene != "resting" else 2500)
            info = page.evaluate("window.rookOverlay && window.rookOverlay.info()")
            name = f"page-{a.anchor}-{scene}"
            raw = os.path.join(OUT, f"{name}-alpha.png")
            page.screenshot(path=raw, omit_background=True)
            page.close()
            shot = Image.open(raw).convert("RGBA")
            strip, centre, bbox = check(shot)
            over = Image.alpha_composite(frame, shot)
            over.save(os.path.join(OUT, f"{name}.png"))
            os.remove(raw)
            ok = strip == 0 and centre == 0
            bad |= not ok
            print(f"{scene:9s} info={info} strip_alpha_max={strip} centre_alpha_max={centre} drawn_bbox={bbox}"
                  f" {'OK' if ok else 'COVERS STRIP/CENTRE'} {' | '.join(logs)[:300]}")
        browser.close()
    frame.convert("RGB").save(os.path.join(OUT, "game-frame.png"))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
