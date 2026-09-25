"""lead.html -> PDF (A4) + PNG каждой страницы для проверки + список переполненных страниц."""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BUILD = Path(__file__).resolve().parent
ROOT = BUILD.parent
OUT_PDF = ROOT / f"{ROOT.name}.pdf"
PNG = BUILD / "pages"
PNG.mkdir(exist_ok=True)

IMAGES = ROOT / "images"


def to_jpeg(browser, png: Path, max_side: int = 1600, quality: int = 84) -> None:
    """PNG -> JPEG рядом (Pillow нет — пережимаем тем же Chromium), до max_side по длинной стороне."""
    jpg = png.with_suffix(".jpg")
    if jpg.exists() and jpg.stat().st_mtime >= png.stat().st_mtime:
        return
    pg = browser.new_page()
    pg.goto(png.as_uri())
    w, h = pg.evaluate("[document.images[0].naturalWidth, document.images[0].naturalHeight]")
    k = min(1, max_side / max(w, h))
    w, h = round(w * k), round(h * k)
    pg.set_viewport_size({"width": w, "height": h})
    # страница самой картинки (file: → file: разрешено), растягиваем img на весь кадр
    pg.evaluate(f"""() => {{ document.body.style.margin = '0'; document.body.style.background = '#fff';
        const i = document.images[0]; i.style.cssText = 'width:{w}px;height:{h}px;display:block;margin:0'; }}""")
    pg.screenshot(path=str(jpg), type="jpeg", quality=quality, full_page=False)
    pg.close()


with sync_playwright() as pw:
    browser = pw.chromium.launch()
    for png in IMAGES.glob("*.png"):
        to_jpeg(browser, png)
    page = browser.new_page(viewport={"width": 794, "height": 1123})
    page.goto((BUILD / "lead.html").as_uri(), wait_until="networkidle")
    page.evaluate("document.fonts.ready")
    fonts = page.evaluate("[...document.fonts].filter(f => f.status === 'loaded').map(f => f.family)")
    over = page.evaluate("""[...document.querySelectorAll('.page')].map((p, i) => {
        const r = p.getBoundingClientRect();
        let maxBottom = 0;
        p.querySelectorAll('*').forEach(el => {
          if (el.closest('.cover') || el.classList.contains('num') || el.classList.contains('brand')) return;
          const b = el.getBoundingClientRect().bottom - r.top; if (b > maxBottom) maxBottom = b; });
        return {page: i + 1, bottom: Math.round(maxBottom)};
    })""")
    for i, el in enumerate(page.query_selector_all(".page"), 1):
        el.screenshot(path=str(PNG / f"p{i:02d}.png"))
    page.pdf(path=str(OUT_PDF), format="A4", print_background=True, margin={"top": "0", "right": "0", "bottom": "0", "left": "0"})
    browser.close()

print("fonts:", sorted(set(fonts)))
limit = 1123 - 80
for o in over:
    flag = "  <-- ПЕРЕПОЛНЕНА" if o["bottom"] > limit else ""
    print(f"p{o['page']:02d} низ контента {o['bottom']}px{flag}")
print(OUT_PDF, round(OUT_PDF.stat().st_size / 1e6, 1), "MB")
