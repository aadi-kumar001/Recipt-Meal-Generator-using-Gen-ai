"""Generate one SVG illustration per recipe -> static/images/recipes/<id>.svg
Usage: python tools/generate_images.py"""
import hashlib, json, random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FOOD = ["#ef4444", "#16a34a", "#f59e0b", "#a3e635", "#f97316", "#facc15", "#84cc16", "#dc2626"]

def svg_for(r):
    rng = random.Random(int(hashlib.md5(r["id"].encode()).hexdigest(), 16))
    bits = "".join(
        f'<circle cx="{200 + rng.randint(-95, 95)}" cy="{125 + rng.randint(-45, 45)}" '
        f'r="{rng.randint(7, 16)}" fill="{rng.choice(FOOD)}" opacity="0.85"/>' for _ in range(16))
    return f'''<svg viewBox="0 0 400 250" xmlns="http://www.w3.org/2000/svg">
<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{r["color"]}"/><stop offset="1" stop-color="#ffffff"/></linearGradient></defs>
<rect width="400" height="250" fill="url(#g)"/>
<ellipse cx="200" cy="135" rx="150" ry="95" fill="#00000012"/>
<ellipse cx="200" cy="125" rx="145" ry="92" fill="#ffffff"/>
<ellipse cx="200" cy="125" rx="118" ry="72" fill="#f8fafc" stroke="#e2e8f0" stroke-width="3"/>
{bits}
<text x="200" y="150" font-size="72" text-anchor="middle">{r["emoji"]}</text>
</svg>'''

def main():
    recipes = json.loads((ROOT / "data" / "recipes.json").read_text(encoding="utf-8"))
    out = ROOT / "static" / "images" / "recipes"
    out.mkdir(parents=True, exist_ok=True)
    for r in recipes:
        (out / f"{r['id']}.svg").write_text(svg_for(r), encoding="utf-8")
    print(f"Generated {len(recipes)} images in {out}")

if __name__ == "__main__":
    main()
