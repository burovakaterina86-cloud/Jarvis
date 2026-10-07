"""Сгенерированные картинки для лидмагнитов и каруселей: сначала Codex, потом kie.ai.

    python -m integrations.visuals.imagegen "промпт" <путь.png> [--ratio 3:4] [--res 2K] [--only codex|kie]
                                            [--ref фото-образец.png ...]

Порядок — её решение 2026-09-25:
1. **Codex** (`codex exec` + встроенный навык `$imagegen`, модель gpt-image) — в рамках её подписки
   ChatGPT Plus, отдельно не платим. Картинки едят лимит Codex в 3-5 раз быстрее текста.
2. **kie.ai** (ключ `KIE_API_KEY` в `.env`) — если у Codex кончился лимит или он не сработал.
   Платно, кредитами kie.ai. Модель — по задаче (её решение 2026-09-25):
   - внешность сохранять не нужно — Grok Imagine 2.0, не вышло — GPT Image 2.5;
   - нужно сохранить внешность (`--ref фото`) — Nano Banana 2 в 2K (её выбор по сходству), не вышло —
     GPT Image 2.5 в 2K. Фото-образцы сначала загружаются в kie.ai (хранятся там 3 дня).

Картинки только реалистичные — живые фотокадры, не графика и не иллюстрация (её решение
2026-09-25): к каждому промпту дописывается `REALISM`.

Печатает путь и кто нарисовал; если пришлось уйти на kie.ai — причину в stderr.
Текст на картинках не заказывай: надписи накладываются вёрсткой.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

KIE_BASE = "https://api.kie.ai"
# загрузка файлов у kie.ai на отдельном хосте (api.kie.ai отвечает 404)
KIE_UPLOAD = "https://kieai.redpandaai.co/api/file-base64-upload"
# модели kie.ai: пропорции, которые умеет, есть ли параметр resolution, поле для фото-образцов
KIE_SPECS = {
    "grok-imagine-image-2-0/text-to-image": {"ratios": ("1:1", "2:3", "3:2", "16:9", "9:16"),
                                            "resolution": False},
    "gpt-image-2-5-flare-text-to-image": {"ratios": ("1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9", "21:9"),
                                          "resolution": True},
    # 4:5 и 5:4 kie.ai у этой модели отклоняет (проверено 2026-09-25), хотя в документации они есть
    "gpt-image-2-5-flare-image-to-image": {"ratios": ("1:1", "2:3", "3:2", "3:4", "4:3",
                                                      "9:16", "16:9", "21:9"),
                                           "resolution": True, "refs_field": "input_urls"},
    "nano-banana-2": {"ratios": ("1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"),
                      "resolution": True, "refs_field": "image_input"},
}
# порядок попыток: без образцов внешности и с ними
KIE_TEXT = ("grok-imagine-image-2-0/text-to-image", "gpt-image-2-5-flare-text-to-image")
# Nano Banana 2 — самая дорогая, поэтому только для сохранения её внешности. Сначала была запасной;
# после сравнения на одном запросе она выбрала её: «второй ближе» (2026-09-25) — теперь основная для её кадров.
KIE_REF = ("nano-banana-2", "gpt-image-2-5-flare-image-to-image")
KIE_REF_RESOLUTION = "2K"
# образец СТИЛЯ (почерк, приём) — не внешности: только GPT Image 2.5, без правил про лицо и фотореализм
KIE_STYLE = ("gpt-image-2-5-flare-image-to-image",)
# Её инструкция IDENTITY LOCK 2026-09-25 (дословно — `essa-ai/IDENTITY_LOCK.md`), переведена для моделей.
# Её фото передаётся в модель всегда (HAS_IDENTITY_REFERENCE); словесного описания её лица здесь нет —
# инструкция прямо запрещает заменять фотографию описанием и делать лицо худее/глаже.
IDENTITY_LOCK = (
    "IDENTITY LOCK. The woman in the reference photos is a real person, Ekaterina. Her appearance is an "
    "UNCHANGEABLE element: she must look like the very same real person from the reference photos, not like a "
    "similar woman. IMAGE 1 is her PRIMARY IDENTITY REFERENCE; any other photos of her are the same person from "
    "other angles and serve identity only. Do not create her from a text description. "
    "Preserve as precisely as possible: face shape and proportions; the distances and proportions between eyes, "
    "nose and lips; eye shape; how the eyes are set; eye colour; eyebrow shape and position; nose shape; lip "
    "shape; jawline; chin; forehead shape; cheekbones; natural facial asymmetry; age; skin tone; natural skin "
    "texture; moles, freckles and other individual features where visible; hairline; hair colour; real body "
    "proportions. "
    "Do NOT, unless explicitly requested: make her younger; make the face more symmetrical; make the skin "
    "plastic or overly smooth; enlarge the eyes; enlarge the lips; make the nose smaller; change the chin; "
    "change the face oval; make the face thinner; change the body build. "
    # её правило 2026-09-25 (дословно — `essa-ai/IDENTITY_LOCK.md`, п. 5)
    "Her face and appearance are unchanged relative to the reference: identical facial features - the shape of "
    "the cheekbones, nose and lips, the shape and colour of the eyes, the eyebrow shape, the jaw and chin are "
    "fixed. Do not make her older and do not add age. Hair colour strictly as in the reference photo. Do not "
    "change her identity, face, body build and figure proportions. "
    "The face is crystal-clear, ultra-sharp, focus strictly on the eyes and skin texture - NO BLUR, NO SOFT "
    "FOCUS, NO SMOOTHING. Every pore, every eyebrow hair and eyelash is detailed. "
    "If beautiful stylisation conflicts with likeness, likeness always wins. ")
KEEP_FACE = (IDENTITY_LOCK +
             # её правило 2026-09-25: «причёску, одежду обязательно меняем»
             "Hairstyle and clothing MUST be different from the reference photos in every new image (a new "
             "hairstyle and a new outfit that suit the scene); only the hair colour stays exactly as in the "
             "reference. Pose, camera angle and setting may change. "
             # её слова 2026-09-25: «цвет волос запомни — холодный бежевый блонд»
             "Her hair colour is cool beige ash blonde, as in the reference photos - never golden, honey or brown. "
             # её слова 2026-09-25: «не делай слишком строгие фото… одежда современная, но не строгая»
             "Her clothing is modern and relaxed, casual-chic (soft knitwear, relaxed shirts, easy trousers, "
             "soft textures) - never strict classic business wear, no formal suits or stiff blazers.")


#: Её identity reference set — порядок важен: первое — главное (IMAGE 1). Её пример 2026-09-25:
#: `reference_images = [main, front, three_quarter]` → в модель, которая умеет image conditioning.
IDENTITY_REFS = [
    Path("essa-ai/photo/portraits/face-main-selfie-black.jpg"),  # main: её выбор 2026-09-25, анфас, резкое
    Path("essa-ai/photo/portraits/face-front-white.jpg"),    # её референс 2026-09-25: анфас, белый фон, резкий
    Path("essa-ai/photo/portraits/face-selfie-2.jpg"),       # анфас, высокое разрешение
    Path("essa-ai/photo/portraits/face-front-studio.png"),   # front: студийный анфас
    Path("essa-ai/photo/portraits/face-reference.jpg"),      # three_quarter
    Path("essa-ai/photo/portraits/face-profile-left.png"),
    Path("essa-ai/photo/portraits/face-profile-right.png"),
]


def require_identity(refs, root: Path | None = None) -> list:
    """HAS_IDENTITY_REFERENCE: её фото обязательно передаётся в модель, иначе генерации нет.
    Не передали — сначала ищем её основной набор в сохранённых ассетах проекта (её инструкция, п. 2)."""
    base = root or ROOT
    found = [Path(r) for r in refs or () if Path(r).is_file()]
    if not found:
        found = [base / r for r in IDENTITY_REFS if (base / r).is_file()]
    if not found:
        raise NoIdentityReference(
            "нет её фотографии — без исходного фото невозможно гарантировать сохранение внешности "
            "(essa-ai/IDENTITY_LOCK.md, п. 2); генерацию не выполняю")
    return found


def edit_prompt(scope: str, scene: str = "") -> str:
    """Правка её настоящего фото: лицо не перерисовывается, меняется только перечисленное (её схема 2026-09-25:
    «твоё фото → identity lock → правка фона/стиля → локальные изменения → обложка»)."""
    return (IDENTITY_LOCK +
            "Her hair colour stays cool beige ash blonde. "
            f"EDIT IMAGE 1. EDIT SCOPE - change ONLY: {scope}. Everything else about the person - the whole face, "
            "head, expression, skin and body - stays faithful to IMAGE 1, as in a careful photo retouch, not a "
            "new portrait. Result is a real photograph, the face is always in sharp focus, no text or logos."
            + (f"\n\nTarget: {scene}" if scene else ""))


REALISM = (
    "Photorealistic: a real photograph shot on a professional camera, natural light, real textures, "
    "real people and objects, shallow depth of field only for the background - the face is always in sharp "
    "focus. Not an illustration, not flat "
    "graphics, not a 3D render, not a cartoon. No text, letters or logos in the image."
)
CODEX_TIMEOUT_S = 600


class ImageGenError(Exception):
    """Картинку получить не удалось."""



class NoIdentityReference(ImageGenError):
    """Кадр с ней без её фото — её инструкция (`essa-ai/IDENTITY_LOCK.md`, п. 2): генерацию не выполнять."""


class CodexLimit(ImageGenError):
    """У Codex кончился лимит подписки."""


@dataclass
class Result:
    path: Path
    provider: str  # "codex" | "kie"
    note: str = ""  # почему не Codex, если ушли на kie.ai


# --- Codex ---

def codex_prompt(prompt: str, filename: str, aspect_ratio: str, refs: bool = False, raw: bool = False) -> str:
    if raw:   # образец стиля: промпт как есть, без лица и фотореализма
        return (f"Use $imagegen to generate exactly one image. Aspect ratio {aspect_ratio}, high resolution.\n"
                f"The attached image(s) are style references.\n{prompt}\n\n"
                f"Save the final PNG as {filename} in the current working directory. "
                "Do not create any other files. Reply with only the saved file path.")
    keep = f"The attached image(s) are reference photos of the person. {KEEP_FACE}\n\n" if refs else ""
    return (
        f"Use $imagegen to generate exactly one image. Aspect ratio {aspect_ratio}, high resolution.\n"
        f"{keep}Image description:\n{prompt}\n\n{REALISM}\n\n"
        f"Save the final PNG as {filename} in the current working directory. "
        "Do not create any other files. Reply with only the saved file path."
    )


def parse_codex_events(output: str) -> tuple[str | None, str | None]:
    """Из JSONL `codex exec --json` — (thread_id, текст ошибки или None). Не-JSON строки пропускаем."""
    thread, error = None, None
    for line in output.splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if not isinstance(ev, dict):
            continue
        if ev.get("type") == "thread.started":
            thread = ev.get("thread_id")
        elif ev.get("type") == "error" and ev.get("message"):
            error = error or ev["message"]
        elif ev.get("type") == "turn.failed":
            error = error or (ev.get("error") or {}).get("message") or "turn failed"
    return thread, error


def run_codex(cmd: list[str], cwd: Path) -> tuple[int, str]:
    """Запускает `codex exec`; ПОСЛЕДНИЙ элемент `cmd` — промпт, он уходит через stdin, а не аргументом.

    На Windows `codex` — это `codex.cmd`: cmd.exe обрезает аргумент на первом переводе строки и исполняет
    `& … ` внутри него. Поэтому запускаем `node …/codex.js` напрямую (как `codex_bridge`), а промпт — в stdin.
    """
    from runtime.codex_bridge import default_codex_cmd
    try:
        base = default_codex_cmd()
    except FileNotFoundError as e:
        raise ImageGenError("codex не установлен") from e
    *args, prompt = cmd[1:]
    try:
        from runtime import secretenv
        p = subprocess.run([*base, *args, "-"], cwd=cwd, input=prompt, env=secretenv.scrub(), capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=CODEX_TIMEOUT_S)
    except subprocess.TimeoutExpired as e:
        raise ImageGenError(f"codex не ответил за {CODEX_TIMEOUT_S} с") from e
    return p.returncode, p.stdout


def generate_codex(prompt: str, dest: Path, aspect_ratio: str = "3:4", *, refs=(), raw: bool = False,
                   run=run_codex, home: Path | None = None) -> Path:
    dest = Path(dest).resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Codex пишет только во временную папку (workspace-write даёт ему запись в -C): если бы это была папка
    # результата, а она в корне проекта, он мог бы менять и .claude/hooks. Готовый файл копируем сами.
    with tempfile.TemporaryDirectory(prefix="jarvis-img-") as tmp:
        work = Path(tmp)
        cmd = ["codex", "exec", "--skip-git-repo-check", "--ephemeral", "-s", "workspace-write",
               "-C", str(work), "--json",
               *[f"--image={Path(r).resolve()}" for r in refs],
               codex_prompt(prompt, dest.name, aspect_ratio, refs=bool(refs), raw=raw)]
        _, output = run(cmd, work)
        thread, error = parse_codex_events(output)
        if error and "usage limit" in error.lower():
            raise CodexLimit(error)
        made = work / dest.name
        if made.is_file():
            shutil.copyfile(made, dest)
            return dest
    # Codex мог оставить картинку у себя: ~/.codex/generated_images/<thread>/
    gen_dir = (home or Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")) / "generated_images"
    if thread and (gen_dir / thread).is_dir():
        pngs = sorted((gen_dir / thread).glob("*.png"), key=lambda p: p.stat().st_mtime)
        if pngs:
            shutil.copyfile(pngs[-1], dest)
            return dest
    raise ImageGenError(f"codex не отдал картинку: {error or 'файла нет'}")


# --- kie.ai ---

def require_kie_key(env: dict[str, str] | None = None) -> str:
    if env is None:
        from integrations.radar.keys import load_dotenv

        load_dotenv(only=("KIE_API_KEY",))
        env = os.environ
    key = env.get("KIE_API_KEY")
    if not key:
        raise ImageGenError("нет ключа KIE_API_KEY в .env")
    return key


def _ratio_value(ratio: str) -> float:
    w, h = ratio.split(":")
    return float(w) / float(h)


def fit_ratio(model: str, aspect_ratio: str) -> str:
    """Пропорция, которую модель умеет: та же или ближайшая (4:5 у GPT Image 2.5 -> 3:4)."""
    supported = KIE_SPECS[model]["ratios"]
    if aspect_ratio in supported:
        return aspect_ratio
    want = _ratio_value(aspect_ratio)
    return min(supported, key=lambda r: abs(_ratio_value(r) - want))


def kie_task_body(model: str, prompt: str, aspect_ratio: str = "3:4", resolution: str = "2K",
                  ref_urls: list[str] | None = None, raw: bool = False) -> dict:
    spec = KIE_SPECS[model]
    if raw:
        text = prompt
    else:
        text = f"{prompt}\n\n{KEEP_FACE}\n\n{REALISM}" if ref_urls else f"{prompt}\n\n{REALISM}"
    inp = {"prompt": text, "aspect_ratio": fit_ratio(model, aspect_ratio)}
    if spec["resolution"]:
        inp["resolution"] = resolution
    if ref_urls:
        inp[spec["refs_field"]] = list(ref_urls)
    if model == "nano-banana-2":
        inp["output_format"] = "png"
    return {"model": model, "input": inp}


def kie_upload(path: Path, key: str, api=None) -> str:
    """Фото-образец в kie.ai (base64) -> ссылка для модели. Файл у них живёт 3 дня."""
    import base64
    import mimetypes

    path = Path(path)
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    body = {"base64Data": f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii"),
            "uploadPath": "jarvis-refs", "fileName": path.name}
    res = (api or kie_http)("POST", KIE_UPLOAD, key, body)
    url = (res.get("data") or {}).get("downloadUrl")
    if not url:
        raise ImageGenError(f"образец {path.name} не загрузился: {res.get('msg') or res}")
    return url


# Хосты kie.ai: API и загрузка файлов (https://docs.kie.ai/file-upload-api/quickstart — база `kieai.redpandaai.co`)
KIE_HOSTS = {"api.kie.ai", "kieai.redpandaai.co"}


def kie_http(method: str, path: str, key: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    url = path if path.startswith("https://") else KIE_BASE + path
    if urllib.parse.urlsplit(url).hostname not in KIE_HOSTS:   # ключ уходит только на хосты kie.ai
        raise ImageGenError(f"адрес не из kie.ai, ключ не отправляю: {url[:60]}")
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise ImageGenError(f"kie.ai ответил {e.code}: {e.read().decode('utf-8', 'replace')[:300]}") from e
    except (urllib.error.URLError, TimeoutError, ValueError) as e:   # сеть, таймаут, не-JSON в ответе
        raise ImageGenError(f"kie.ai недоступен или ответил не так: {type(e).__name__}") from e


def http_download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=120) as resp:
        dest.write_bytes(resp.read())


def generate_kie(prompt: str, dest: Path, aspect_ratio: str = "3:4", resolution: str = "2K", *, refs=(),
                 style: bool = False, raw: bool = False,
                 key: str | None = None, api=kie_http, download=http_download, sleep=time.sleep,
                 timeout_s: int = 300) -> Path:
    """Модели kie.ai по очереди: без образцов — `KIE_TEXT`, с образцами внешности — `KIE_REF` в 2K."""
    key = key or require_kie_key()
    ref_urls = [kie_upload(r, key, api) for r in refs] if refs else None
    chain = KIE_STYLE if style else (KIE_REF if ref_urls else KIE_TEXT)
    if ref_urls:
        resolution = KIE_REF_RESOLUTION
    errors = []
    for model in chain:
        try:
            return _kie_task(model, prompt, dest, aspect_ratio, resolution, key=key, api=api, ref_urls=ref_urls,
                             raw=style or raw,
                             download=download, sleep=sleep, timeout_s=timeout_s)
        except ImageGenError as e:
            errors.append(f"{model}: {e}")
    raise ImageGenError("kie.ai: " + "; ".join(errors))


def _kie_task(model, prompt, dest, aspect_ratio, resolution, *, key, api, ref_urls, download, sleep,
              timeout_s, raw=False) -> Path:
    created = api("POST", "/api/v1/jobs/createTask", key,
                  kie_task_body(model, prompt, aspect_ratio, resolution, ref_urls, raw=raw))
    task_id = (created.get("data") or {}).get("taskId")
    if created.get("code") != 200 or not task_id:
        raise ImageGenError(f"задача не создана: {created.get('msg') or created}")

    waited = 0
    while waited <= timeout_s:
        info = api("GET", f"/api/v1/jobs/recordInfo?taskId={task_id}", key).get("data") or {}
        state = info.get("state")
        if state == "success":
            try:
                urls = json.loads(info.get("resultJson") or "{}").get("resultUrls") or []
            except ValueError as e:
                raise ImageGenError("задача выполнена, но ответ с ссылкой не разобрать") from e
            if not urls:
                raise ImageGenError("задача выполнена, но ссылки на картинку нет")
            download(urls[0], dest)
            return dest
        if state == "fail":
            raise ImageGenError(f"генерация не удалась: {info.get('failMsg') or info.get('failCode')}")
        sleep(5)
        waited += 5
    raise ImageGenError(f"не дождался картинки за {timeout_s} с")


# --- порядок ---

def generate(prompt: str, dest: Path, aspect_ratio: str = "3:4", resolution: str = "2K", *,
             refs=(), style_refs=(), edit_scope: str = "", her: bool = False, only: str | None = None,
             codex=generate_codex, kie=generate_kie) -> Result:
    """`refs` — её фото-образцы, если внешность нужно сохранить; пусто — внешность не важна.
    `edit_scope` — правка её фото `refs[0]` вместо новой генерации: меняется только перечисленное."""
    dest = Path(dest)
    note = ""
    if her or edit_scope:   # кадр с ней: её фото обязательно (HAS_IDENTITY_REFERENCE)
        refs = require_identity(refs)
    if edit_scope:
        if not refs:
            raise ImageGenError("правка фото: нужно её фото первым --ref")
        prompt = edit_prompt(edit_scope, prompt)
    if only != "kie":
        try:
            if edit_scope:
                return Result(codex(prompt, dest, aspect_ratio, refs=refs, raw=True), "codex")
            if style_refs:
                return Result(codex(prompt, dest, aspect_ratio, refs=style_refs, raw=True), "codex")
            return Result(codex(prompt, dest, aspect_ratio, refs=refs), "codex")
        except CodexLimit as e:
            note = f"у Codex кончился лимит подписки ({e})"
        except ImageGenError as e:
            note = f"Codex не сработал: {e}"
        if only == "codex":
            raise ImageGenError(note)
    try:
        if edit_scope:
            return Result(kie(prompt, dest, aspect_ratio, resolution, refs=refs, raw=True), "kie", note)
        if style_refs:
            return Result(kie(prompt, dest, aspect_ratio, resolution, refs=style_refs, style=True), "kie", note)
        return Result(kie(prompt, dest, aspect_ratio, resolution, refs=refs), "kie", note)
    except ImageGenError as e:
        raise ImageGenError("; ".join(filter(None, [note, str(e)]))) from e


def main() -> int:
    for stream in (sys.stdout, sys.stderr):  # консоль Windows по умолчанию не UTF-8
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    p = argparse.ArgumentParser(description="Картинка: Codex по подписке, запасной — kie.ai")
    p.add_argument("prompt")
    p.add_argument("dest", type=Path)
    p.add_argument("--ratio", default="3:4")
    p.add_argument("--res", default="2K", choices=["1K", "2K", "4K"])
    p.add_argument("--only", choices=["codex", "kie"])
    p.add_argument("--her", action="store_true",
                   help="на кадре она: без её фото в --ref генерация не выполняется (её IDENTITY LOCK)")
    p.add_argument("--edit", default="", help="правка её фото (первый --ref): что менять, например "
                   "«фон на светло-лавандовый, одежду на кремовый свитер»; промпт — какой должна стать сцена")
    p.add_argument("--style-ref", action="append", type=Path, default=[],
                   help="образец стиля (почерк, приём), не внешности: промпт идёт как есть")
    p.add_argument("--ref", action="append", type=Path, default=[],
                   help="фото-образец, если внешность нужно сохранить (можно несколько раз)")
    a = p.parse_args()
    try:
        r = generate(a.prompt, a.dest, a.ratio, a.res, refs=a.ref, style_refs=a.style_ref, edit_scope=a.edit,
                     her=a.her or bool(a.ref), only=a.only)
    except ImageGenError as e:
        print(f"ОШИБКА: {e}", file=sys.stderr)
        return 1
    if r.note:
        print(f"kie.ai вместо Codex: {r.note}", file=sys.stderr)
    print(f"{r.path} ({r.provider})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
