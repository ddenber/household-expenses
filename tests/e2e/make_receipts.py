"""Renders receipt images for the e2e test (runtime-generated, nothing binary is committed)."""
import sys
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
today = date.today().strftime("%d/%m/%Y")


def render(name: str, supplier: str, total: str):
    img = Image.new("RGB", (1000, 640), "white")
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype(FONT, 40)
    for i, line in enumerate([supplier, f"Data: {today}", "Qumesht 2.50", f"TOTAL {total} EUR"]):
        d.text((40, 40 + i * 120), line, fill="black", font=f)
    img.save(out / name)


render("receipt-grocery.png", "CONAD MARKET", "85.00")
render("receipt-card.png", "ELEKTRO SHOP", "120.00")
