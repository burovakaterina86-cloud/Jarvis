#!/usr/bin/env python3
"""Prepare an existing local video for reversible scroll seeking; no API calls."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from fractions import Fraction


def run(args):
    result = subprocess.run([str(x) for x in args], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"Command failed: {args[0]}")
    return result.stdout


def executable(value, fallback):
    candidate = value or shutil.which(fallback)
    if not candidate:
        raise ValueError(f"Не найден {fallback}; задайте путь соответствующим параметром.")
    path = Path(candidate).expanduser().resolve()
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError(f"Недоступен исполняемый файл: {path}")
    run([path, '-version'])
    return path


def probe(ffprobe, source):
    raw = json.loads(run([ffprobe, '-v', 'error', '-show_entries',
                         'stream=codec_type,codec_name,width,height,avg_frame_rate,r_frame_rate,has_b_frames:format=duration,size',
                         '-of', 'json', source]))
    streams = raw.get('streams', [])
    video = next((item for item in streams if item.get('codec_type') == 'video'), None)
    if not video or not video.get('width') or not video.get('height'):
        raise ValueError('В файле нет пригодного видеопотока.')
    fps = None
    for field in ('avg_frame_rate', 'r_frame_rate'):
        try:
            candidate = Fraction(video.get(field, '0/1'))
            if candidate > 0:
                fps = candidate
                break
        except (ValueError, ZeroDivisionError):
            pass
    duration = float(raw.get('format', {}).get('duration', 0))
    if fps is None or not math.isfinite(duration) or duration <= 0:
        raise ValueError('Не удалось определить длительность или частоту кадров.')
    return {'width': int(video['width']), 'height': int(video['height']),
            'fps': str(fps), 'duration': duration, 'codec': video.get('codec_name'),
            'b_frames': int(video.get('has_b_frames', 0)),
            'audio_streams': sum(x.get('codec_type') == 'audio' for x in streams),
            'bytes': int(raw['format'].get('size', source.stat().st_size))}


def main():
    parser = argparse.ArgumentParser(description='Подготовить локальный MP4 под скролл: H.264, плотный GOP, без аудио, без upscale, постер из готового файла.')
    parser.add_argument('input', type=Path)
    parser.add_argument('output', nargs='?', type=Path, help='Новый .mp4; существующие файлы не перезаписываются.')
    parser.add_argument('--inspect', action='store_true', help='Только показать метаданные, без перекодирования.')
    parser.add_argument('--ffmpeg', default=os.environ.get('SITE_BUILDER_FFMPEG'))
    parser.add_argument('--ffprobe', default=os.environ.get('SITE_BUILDER_FFPROBE'))
    parser.add_argument('--max-edge', type=int, default=1920)
    parser.add_argument('--max-fps', type=int, default=30)
    parser.add_argument('--gop', type=int, default=4)
    parser.add_argument('--crf', type=int, default=21)
    args = parser.parse_args()
    if args.max_edge < 2 or not 1 <= args.max_fps <= 60 or not 1 <= args.gop <= 30 or not 0 <= args.crf <= 51:
        raise ValueError('Проверьте max-edge (>=2), max-fps (1–60), gop (1–30), crf (0–51).')
    source = args.input.expanduser().resolve()
    if not source.is_file():
        raise ValueError(f'Нет исходного локального файла: {source}')
    ffmpeg = executable(args.ffmpeg, 'ffmpeg')
    sibling = ffmpeg.with_name('ffprobe.exe' if ffmpeg.suffix == '.exe' else 'ffprobe')
    ffprobe = executable(args.ffprobe or (str(sibling) if sibling.is_file() else None), 'ffprobe')
    original = probe(ffprobe, source)
    if args.inspect:
        print(json.dumps({'source': source.name, **original}, ensure_ascii=False, indent=2))
        return
    if args.output is None:
        raise ValueError('Укажите output.mp4 или --inspect.')
    output = args.output.expanduser().resolve()
    if output == source or output.suffix.lower() != '.mp4':
        raise ValueError('Результат должен быть отдельным новым .mp4, не исходником.')
    poster = output.with_suffix('.poster.jpg')
    manifest = output.with_suffix('.media.json')
    for file in (output, poster, manifest):
        if file.exists():
            raise ValueError(f'Файл уже существует; выберите другое имя: {file}')
    ratio = min(1.0, args.max_edge / max(original['width'], original['height']))
    width = max(2, int(original['width'] * ratio) // 2 * 2)
    height = max(2, int(original['height'] * ratio) // 2 * 2)
    fps = min(Fraction(original['fps']), Fraction(args.max_fps))
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.scroll-encode-', dir=output.parent) as scratch:
        temp = Path(scratch)
        clip = temp / 'video.mp4'
        jpg = temp / 'poster.jpg'
        run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-i', source, '-map', '0:v:0',
             '-an', '-sn', '-dn', '-vf', f'scale={width}:{height}:flags=lanczos,fps={fps},format=yuv420p',
             '-c:v', 'libx264', '-preset', 'medium', '-crf', args.crf,
             '-g', args.gop, '-keyint_min', args.gop, '-sc_threshold', '0',
             '-bf', '0', '-refs', '1', '-movflags', '+faststart', clip])
        encoded = probe(ffprobe, clip)
        if encoded['audio_streams'] or encoded['b_frames'] or encoded['width'] > original['width'] or encoded['height'] > original['height']:
            raise RuntimeError('Проверка закодированного файла не прошла.')
        run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-i', clip, '-frames:v', '1', '-q:v', '2', jpg])
        frames = run([ffprobe, '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'frame=key_frame', '-of', 'csv=p=0', clip])
        flags = [line.strip().split(',')[0] for line in frames.splitlines() if line.strip().split(',')[0] in ('0', '1')]
        keys = [i for i, flag in enumerate(flags) if flag == '1']
        gaps = [b - a for a, b in zip(keys, keys[1:])]
        if not keys or max(gaps, default=0) > args.gop:
            raise RuntimeError('Проверка интервалов ключевых кадров не прошла.')
        record = {'source': source.name, 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                  'original': original, 'delivery': encoded, 'gop_requested': args.gop,
                  'max_keyframe_gap': max(gaps, default=0), 'frames': len(flags),
                  'poster': poster.name, 'video': output.name}
        for target, data in ((output, clip.read_bytes()), (poster, jpg.read_bytes()),
                             (manifest, (json.dumps(record, ensure_ascii=False, indent=2) + '\n').encode())):
            with target.open('xb') as handle:
                handle.write(data)
    print(json.dumps({'video': str(output), 'poster': str(poster), 'manifest': str(manifest), **encoded}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f'Ошибка: {error}', file=sys.stderr)
        sys.exit(1)
