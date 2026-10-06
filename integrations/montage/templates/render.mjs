// Покадровый рендер прозрачного оверлея (запускает integrations/montage/render.py).
// Окружение: MONTAGE_PUPPETEER (папка puppeteer-core), MONTAGE_BROWSER (Edge/Chrome), MONTAGE_HTML, MONTAGE_FRAMES,
//            MONTAGE_FPS, MONTAGE_DUR, MONTAGE_T0, MONTAGE_T1 (необязательные: рендер куска, для проверки)
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const require = createRequire(import.meta.url);
const puppeteer = require(process.env.MONTAGE_PUPPETEER);
const html = process.env.MONTAGE_HTML;
const outDir = process.env.MONTAGE_FRAMES;
const fps = +(process.env.MONTAGE_FPS || 30);
const dur = +process.env.MONTAGE_DUR;
const t0 = +(process.env.MONTAGE_T0 || 0);
const t1 = +(process.env.MONTAGE_T1 || dur);
fs.mkdirSync(outDir, { recursive: true });

const browser = await puppeteer.launch({
  executablePath: process.env.MONTAGE_BROWSER,
  headless: true,
  args: ["--allow-file-access-from-files", "--disable-gpu", "--hide-scrollbars", "--force-color-profile=srgb"],
});
const page = await browser.newPage();
await page.setViewport({ width: 1080, height: 1920, deviceScaleFactor: 1 });
await page.goto(pathToFileURL(html).href, { waitUntil: "load" });
await page.evaluate(() => document.fonts.ready);
await new Promise(r => setTimeout(r, 400));

let blank = null;
const total = Math.round(dur * fps);
const k0 = Math.round(t0 * fps), k1 = Math.min(total, Math.round(t1 * fps));
const started = Date.now();
for (let k = k0; k < k1; k++) {
  const n = await page.evaluate(tt => window.render(tt), k / fps);
  const file = path.join(outDir, String(k + 1).padStart(5, "0") + ".png");
  if (n === 0) {
    if (!blank) blank = await page.screenshot({ type: "png", omitBackground: true });
    fs.writeFileSync(file, blank);
  } else {
    await page.screenshot({ path: file, type: "png", omitBackground: true });
  }
  if (k % 150 === 0) console.log(`кадр ${k}/${total} (${((Date.now() - started) / 1000).toFixed(0)} с)`);
}
await browser.close();
console.log("готово", k1 - k0, "кадров");
