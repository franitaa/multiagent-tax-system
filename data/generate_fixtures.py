"""Generate synthetic W-2-style image fixtures. No real taxpayer data is used.

These are teaching fixtures, not official IRS forms or realistic tax advice.
The extractor must read pixels; expected.json is used only by tests.
"""

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
LABELS = [
    ("1", "Wages, tips, other compensation"), ("2", "Federal income tax withheld"),
    ("3", "Social security wages"), ("4", "Social security tax withheld"),
    ("5", "Medicare wages and tips"), ("6", "Medicare tax withheld"),
    ("7", "Social security tips"), ("8", "Allocated tips"),
    ("10", "Dependent care benefits"), ("11", "Nonqualified plans"),
]


def font(size):
    for name in ("DejaVuSans.ttf", "Arial.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)


def draw_fixture(path: Path, index: int, *, unreadable=False, invalid_ssn=False):
    image = Image.new("RGB", (1800, 1320), "white")
    draw = ImageDraw.Draw(image)
    draw.text((50, 35), "W-2  Wage and Tax Statement", font=font(42), fill="black")
    draw.text((1510, 40), "2025", font=font(42), fill="black")
    draw.text((50, 100), "SYNTHETIC TEST FIXTURE - NOT FOR FILING", font=font(26), fill="black")
    draw.text((50, 170), "a Employee SSN", font=font(23), fill="black")
    ssn = "123-00-0000" if invalid_ssn else f"901-00-{index:04d}"
    draw.text((50, 205), ssn, font=font(29), fill="black")
    draw.text((900, 170), "b Employer EIN", font=font(23), fill="black")
    draw.text((900, 205), "00-0000000", font=font(29), fill="black")
    draw.text((50, 270), f"c Employer: Example Test Employer {index:02d}", font=font(25), fill="black")
    draw.text((50, 315), f"e Employee: SAMPLE PERSON {index:02d}", font=font(25), fill="black")
    wages = 30000 + (index - 1) * 1234
    withholding = 2000 + (index - 1) * 87
    values = {"1": wages, "2": withholding, "3": wages, "4": 1800,
              "5": wages, "6": 450, "7": 0, "8": 0, "10": 0, "11": 0}
    for pos, (box, label) in enumerate(LABELS):
        x = 50 + (pos % 2) * 850
        y = 390 + (pos // 2) * 140
        draw.rectangle((x, y, x + 850, y + 140), outline="black", width=2)
        draw.text((x + 18, y + 16), f"{box} {label}", font=font(25), fill="black")
        text = "[unreadable scan]" if unreadable and box == "2" else f"{values[box]:,}.00"
        draw.text((x + 24, y + 65), text, font=font(35), fill="black")
    draw.text((50, 1130), "Boxes 12-20: intentionally unused in this basic synthetic example.",
              font=font(23), fill="black")
    draw.text((50, 1180), "One document per image. All names and identifiers are fictional.",
              font=font(23), fill="black")
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, quality=96)
    return {box: f"{value}.00" for box, value in values.items()}


def main():
    expected = {}
    for index in range(1, 11):
        name = f"w2_{index:02d}.jpg"
        expected[name] = draw_fixture(ROOT / "data/fixtures" / name, index)
    (ROOT / "data/fixtures/expected.json").write_text(json.dumps(expected, indent=2) + "\n")
    draw_fixture(ROOT / "demo/w2_review_needed.jpg", 2, unreadable=True)
    draw_fixture(ROOT / "demo/w2_review_clear.jpg", 2)
    draw_fixture(ROOT / "demo/w2_invalid_ssn.jpg", 1, invalid_ssn=True)
    print("Generated 10 clean images and 3 review/privacy fixtures.")


if __name__ == "__main__":
    main()

