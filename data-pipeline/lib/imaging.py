"""이미지 리사이즈·인코딩 공용 헬퍼 (Pillow 만 사용).

- 2_download.py : 원본 저장 시 장변 상한 축소
- 2b_derivatives.py : 웹 표시용 파생본(썸네일 768 / 상세 1600) 생성
- 3_enrich.py : 근접중복 판정용 dHash
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageSequence, ImageStat

# 애니메이션 WebP 로 바꿀 때 프레임 수 상한 — 초과분은 균등 샘플링(재생 시간은 보존)
_MAX_ANIM_FRAMES = 120


def fit_long_edge(img: Image.Image, long_edge: int) -> Image.Image:
    """장변이 long_edge 를 넘으면 비율 유지 축소(LANCZOS). 이하면 그대로 반환."""
    w, h = img.size
    if max(w, h) <= long_edge:
        return img
    scale = long_edge / max(w, h)
    return img.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)


def is_animated(img: Image.Image) -> bool:
    return bool(getattr(img, "is_animated", False)) and getattr(img, "n_frames", 1) > 1


def _web_mode(img: Image.Image) -> Image.Image:
    """WebP 가 받는 모드로 정규화(팔레트·CMYK·16bit 등 → RGB/RGBA)."""
    if img.mode in ("RGB", "RGBA"):
        return img
    has_alpha = img.mode in ("LA", "PA") or (img.mode == "P" and "transparency" in img.info)
    return img.convert("RGBA" if has_alpha else "RGB")


def save_static_webp(img: Image.Image, dest: Path, long_edge: int, quality: int) -> None:
    """정지 WebP 저장(애니메이션이면 첫 프레임)."""
    if is_animated(img):
        img.seek(0)
    frame = _web_mode(img.copy())
    fit_long_edge(frame, long_edge).save(dest, "WEBP", quality=quality, method=6)


def save_animated_webp(img: Image.Image, dest: Path, long_edge: int, quality: int) -> None:
    """애니메이션(GIF 등) → 애니메이션 WebP. 프레임 지연·반복을 보존한다."""
    frames, durations = [], []
    for f in ImageSequence.Iterator(img):
        frames.append(fit_long_edge(_web_mode(f.copy()), long_edge))
        durations.append(int(f.info.get("duration", img.info.get("duration", 100)) or 100))
    if len(frames) > _MAX_ANIM_FRAMES:
        step = len(frames) / _MAX_ANIM_FRAMES
        idx = [int(i * step) for i in range(_MAX_ANIM_FRAMES)]
        total = sum(durations)
        frames = [frames[i] for i in idx]
        durations = [max(20, total // len(frames))] * len(frames)
    # 프레임마다 크기가 다르면 첫 프레임 크기로 맞춘다(WebP 는 단일 캔버스)
    size = frames[0].size
    frames = [f if f.size == size else f.resize(size, Image.LANCZOS) for f in frames]
    frames[0].save(
        dest, "WEBP", save_all=True, append_images=frames[1:], duration=durations,
        loop=img.info.get("loop", 0), quality=quality, method=4,
    )


def dhash(path: Path, size: int = 16, min_std: float = 8.0) -> int | None:
    """차이 해시(dHash, size*size 비트) — 같은 작품의 다른 사진/재인코딩 판정용.

    거의 단색인 이미지(빈 첫 프레임, 흰 배경 선화 등)는 해시가 서로 충돌하므로 None 을 반환한다
    (판정 불가 → 중복으로 보지 않음). 기본 16x16=256bit, 임계 해밍 거리는 호출 측(3_enrich)에서.
    """
    with Image.open(path) as img:
        if is_animated(img):
            img.seek(0)
        gray = img.convert("L")
        if ImageStat.Stat(gray.resize((64, 64))).stddev[0] < min_std:
            return None
        g = gray.resize((size + 1, size), Image.LANCZOS)
        px = list(g.getdata())
    bits = 0
    for row in range(size):
        for col in range(size):
            left = px[row * (size + 1) + col]
            right = px[row * (size + 1) + col + 1]
            bits = (bits << 1) | (1 if left > right else 0)
    return bits


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")
