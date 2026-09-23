"""Портрет владелицы без фона: «Убери фон, раствори край» (2026-09-22).

Её файл `essa-ai/photo/katerina-portrait.webp` снят на светлой стене. Питоновских
пакетов для картинок в `.venv` нет (ни Pillow, ни OpenCV, ни rembg), зато есть
браузер — тот же, которым снимаются слайды. Поэтому фон снимается в canvas:

1. заливка от краёв кадра по светлым пикселям (стена связна и выходит на рамку,
   волосы и пиджак — нет), с проверкой похожести на соседа, чтобы мягкая тень
   на стене отделялась вместе с ней;
2. альфа размывается несколькими проходами box-blur — это и есть «растворить
   край»: границы нет, переход мягкий;
3. остаток светлой каймы срезается растяжкой альфы.

Исходник не трогается: результат ложится отдельным PNG рядом.
Браузера нет — честно возвращаем `None`, а не белый прямоугольник.
"""
from __future__ import annotations

import base64
from pathlib import Path

from . import render

#: Порог светлоты фона. Ниже светлоты стены в тени (справа от лица она
#: заметно темнее): при 150 и при 108 ядро тени справа от лица оставалось
#: серым клином в кадре. Пиджак и волосы ниже порога не проходят: они тёмные
#: либо тёплые, а тёплое отсекает `BG_MAX_CHROMA`.
BG_MIN_LUMA = 74

#: Максимальная разница каналов у фона: стена серая, кожа и волосы — нет.
BG_MAX_CHROMA = 42

#: Насколько сосед может отличаться от уже принятого пикселя фона.
#: Мягкая тень на стене — это плавный переход, а не скачок.
NEIGHBOUR_TOLERANCE = 30

#: Проходы размытия альфы и радиус: край растворяется, а не обрезается ножом.
FEATHER_PASSES = 3
FEATHER_RADIUS = 3

_CUT_JS = r"""
async ({dataUrl, bgMinLuma, bgMaxChroma, tolerance, passes, radius}) => {
  const img = new Image();
  await new Promise((res, rej) => { img.onload = res; img.onerror = rej; img.src = dataUrl; });
  const w = img.width, h = img.height, n = w * h;
  const c = document.createElement('canvas');
  c.width = w; c.height = h;
  const ctx = c.getContext('2d');
  ctx.drawImage(img, 0, 0);
  const im = ctx.getImageData(0, 0, w, h);
  const d = im.data;

  const luma = i => (d[4*i] + d[4*i+1] + d[4*i+2]) / 3;
  const chroma = i => {
    const r = d[4*i], g = d[4*i+1], b = d[4*i+2];
    return Math.max(r,g,b) - Math.min(r,g,b);
  };
  const near = (a, b) => (
    Math.abs(d[4*a] - d[4*b]) + Math.abs(d[4*a+1] - d[4*b+1]) + Math.abs(d[4*a+2] - d[4*b+2])
  ) < tolerance;
  const looksBg = i => luma(i) > bgMinLuma && chroma(i) < bgMaxChroma;

  // 1. заливка от рамки кадра
  const bg = new Uint8Array(n);
  const stack = [];
  const seed = i => { if (!bg[i] && looksBg(i)) { bg[i] = 1; stack.push(i); } };
  for (let x = 0; x < w; x++) { seed(x); seed((h - 1) * w + x); }
  for (let y = 0; y < h; y++) { seed(y * w); seed(y * w + w - 1); }
  while (stack.length) {
    const i = stack.pop();
    const x = i % w, y = (i - x) / w;
    const nb = [];
    if (x > 0) nb.push(i - 1);
    if (x < w - 1) nb.push(i + 1);
    if (y > 0) nb.push(i - w);
    if (y < h - 1) nb.push(i + w);
    for (const j of nb) {
      if (!bg[j] && looksBg(j) && near(i, j)) { bg[j] = 1; stack.push(j); }
    }
  }

  // 2. альфа и её размытие
  let alpha = new Float32Array(n);
  for (let i = 0; i < n; i++) alpha[i] = bg[i] ? 0 : 255;
  const blur = src => {
    const tmp = new Float32Array(n), out = new Float32Array(n);
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        let s = 0, k = 0;
        for (let dx = -radius; dx <= radius; dx++) {
          const xx = x + dx;
          if (xx < 0 || xx >= w) continue;
          s += src[y * w + xx]; k++;
        }
        tmp[y * w + x] = s / k;
      }
    }
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        let s = 0, k = 0;
        for (let dy = -radius; dy <= radius; dy++) {
          const yy = y + dy;
          if (yy < 0 || yy >= h) continue;
          s += tmp[yy * w + x]; k++;
        }
        out[y * w + x] = s / k;
      }
    }
    return out;
  };
  for (let p = 0; p < passes; p++) alpha = blur(alpha);

  // 3. светлая кайма срезается растяжкой: полупрозрачное у фона уходит в ноль
  for (let i = 0; i < n; i++) {
    const a = Math.max(0, Math.min(255, (alpha[i] - 70) * 1.6));
    d[4*i+3] = Math.round(a);
  }
  ctx.putImageData(im, 0, 0);
  return c.toDataURL('image/png');
}
"""

_PROBE_JS = r"""
async (dataUrl) => {
  const img = new Image();
  await new Promise((res, rej) => { img.onload = res; img.onerror = rej; img.src = dataUrl; });
  const c = document.createElement('canvas');
  c.width = img.width; c.height = img.height;
  const ctx = c.getContext('2d');
  ctx.drawImage(img, 0, 0);
  const at = (x, y) => ctx.getImageData(x, y, 1, 1).data[3];
  return {
    top_left: at(2, 2),
    top_right: at(img.width - 3, 2),
    bottom_left: at(2, img.height - 3),
    center: at(Math.round(img.width / 2), Math.round(img.height / 2)),
  };
}
"""

#: Типы, которые умеет читать браузер.
_MIME = {".webp": "image/webp", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


def _data_url(path: Path) -> str:
    mime = _MIME.get(path.suffix.lower(), "application/octet-stream")
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


def _in_browser(js: str, payload):
    """Один короткий заход в тот же браузер, которым снимаются слайды."""
    sync_playwright = render._playwright_module()
    if sync_playwright is None:
        return None
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.goto("about:blank")
        try:
            return page.evaluate(js, payload)
        finally:
            browser.close()


def make_cutout(src, dst) -> Path | None:
    """Снять фон с её портрета и положить результат отдельным файлом.

    Возвращает путь к PNG или `None`, если браузера нет: заглушки с белым
    прямоугольником вместо растворённого края не бывает.
    """
    src, dst = Path(src), Path(dst)
    if not src.is_file():
        return None
    data_url = _in_browser(
        _CUT_JS,
        {
            "dataUrl": _data_url(src),
            "bgMinLuma": BG_MIN_LUMA,
            "bgMaxChroma": BG_MAX_CHROMA,
            "tolerance": NEIGHBOUR_TOLERANCE,
            "passes": FEATHER_PASSES,
            "radius": FEATHER_RADIUS,
        },
    )
    if not data_url:
        return None
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(base64.b64decode(data_url.split(",", 1)[1]))
    return dst


#: Второй её портрет (`katerina-portrait-2.jpg`, прислан 2026-09-23) снят на
#: тёмной стене, а не на светлой. Заливка от краёв по светлым пикселям на нём
#: не работает: фон ниже порога, и вырез не начинается. Зато тёмное здесь и не
#: нужно вырезать — слайд сам тёмный. Поэтому альфа берётся из светлоты:
#: освещённые лицо, руки и пиджак остаются, тёмная стена растворяется в фоне.
#: Порог снят с самого кадра: стена 40–62, ткань пиджака в свету 95–140.
DARK_KEEP_FROM = 52
DARK_KEEP_FULL = 104

_DARK_JS = r"""
async ({dataUrl, from, full, passes, radius}) => {
  const img = new Image();
  await new Promise((res, rej) => { img.onload = res; img.onerror = rej; img.src = dataUrl; });
  const w = img.width, h = img.height, n = w * h;
  const c = document.createElement('canvas');
  c.width = w; c.height = h;
  const ctx = c.getContext('2d');
  ctx.drawImage(img, 0, 0);
  const im = ctx.getImageData(0, 0, w, h);
  const d = im.data;

  // 1. альфа по светлоте: тёмное уходит в фон, освещённое остаётся
  let alpha = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const l = (d[4*i] + d[4*i+1] + d[4*i+2]) / 3;
    alpha[i] = 255 * Math.max(0, Math.min(1, (l - from) / (full - from)));
  }

  // 2. то же размытие, что и у светлого выреза: край растворяется
  const blur = src => {
    const tmp = new Float32Array(n), out = new Float32Array(n);
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      let s = 0, k = 0;
      for (let dx = -radius; dx <= radius; dx++) {
        const xx = x + dx; if (xx < 0 || xx >= w) continue;
        s += src[y*w + xx]; k++;
      }
      tmp[y*w + x] = s / k;
    }
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      let s = 0, k = 0;
      for (let dy = -radius; dy <= radius; dy++) {
        const yy = y + dy; if (yy < 0 || yy >= h) continue;
        s += tmp[yy*w + x]; k++;
      }
      out[y*w + x] = s / k;
    }
    return out;
  };
  for (let p = 0; p < passes; p++) alpha = blur(alpha);

  for (let i = 0; i < n; i++) d[4*i+3] = Math.round(Math.max(0, Math.min(255, alpha[i])));
  ctx.putImageData(im, 0, 0);
  return c.toDataURL('image/png');
}
"""


def make_dark_fade(src, dst) -> Path | None:
    """Портрет с тёмного фона: стена растворяется, освещённый человек остаётся.

    Прямоугольника за краем не остаётся — альфа плавная, без границы.
    Браузера нет — честно `None`, а не чужеродный прямоугольник.
    Исходник не трогается: результат ложится отдельным PNG рядом.
    """
    src, dst = Path(src), Path(dst)
    if not src.is_file():
        return None
    data_url = _in_browser(
        _DARK_JS,
        {
            "dataUrl": _data_url(src),
            "from": DARK_KEEP_FROM,
            "full": DARK_KEEP_FULL,
            "passes": FEATHER_PASSES,
            "radius": FEATHER_RADIUS,
        },
    )
    if not data_url:
        return None
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(base64.b64decode(data_url.split(",", 1)[1]))
    return dst


def alpha_probe(path) -> dict | None:
    """Прозрачность в углах и в центре уже сохранённого файла."""
    path = Path(path)
    if not path.is_file():
        return None
    return _in_browser(_PROBE_JS, _data_url(path))
