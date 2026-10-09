from pathlib import Path
from PIL import Image, ImageChops

src = Path("media/brand/logo.png")
out = Path("static/documents/img")
out.mkdir(parents=True, exist_ok=True)

im = Image.open(src).convert("RGBA")
im.save(out / "logo.png")

r, g, b, _ = im.split()
mn = ImageChops.darker(ImageChops.darker(r, g), b)
ink = mn.point(lambda v: 255 if v < 200 else 0)
w, h = ink.size
rows = [ink.crop((0, y, w, y + 1)).getbbox() is not None for y in range(h)]
start = next((y for y, v in enumerate(rows) if v), 0)
gap, blank, end = max(8, h // 40), 0, h
for y in range(start, h):
    if rows[y]:
        blank = 0
    else:
        blank += 1
        if blank >= gap:
            end = y - blank + 1
            break

mark = im.crop((0, start, w, end))
a = ImageChops.darker(ImageChops.darker(*mark.split()[:3][:2]), mark.split()[2]) if False else None
rm, gm, bm, _ = mark.split()
m = ImageChops.darker(ImageChops.darker(rm, gm), bm)
alpha = m.point(lambda v: 255 if v <= 200 else (0 if v >= 245 else int((245 - v) / 45 * 255)))
mark.putalpha(alpha)
mark = mark.crop(alpha.getbbox())
side = max(mark.size)
sq = Image.new("RGBA", (side, side), (0, 0, 0, 0))
sq.paste(mark, ((side - mark.width) // 2, (side - mark.height) // 2))
sq.thumbnail((256, 256))
sq.save(out / "mark.png")
print("done")