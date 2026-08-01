#!/usr/bin/env python3
"""스테이지 2: 이미지 다운로드 + 검증.

candidates.json 의 각 후보 이미지를 works/{local_id}.ext 로 저장한다.
 - Pillow 로 유효성 검증
 - 래스터 이미지는 장변 MAX_LONG_EDGE 로 축소(용량 관리)
 - 애니메이션 GIF 는 원본 바이트 그대로 저장(움직임 보존)
 - width/height/file_size_mb 기록
실패/파손 이미지는 제외하고 downloaded.json 저장.

실행:  python 2_download.py
"""
from __future__ import annotations

import io
import sys

from PIL import Image

import config
from lib.http import get_bytes
from lib.models import load_records, save_records

_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def _save_image(raw: bytes, mime: str, dest_base) -> tuple[str, int, int, float]:
    """이미지를 저장하고 (파일명, w, h, MB) 반환. 실패 시 예외."""
    ext = _EXT.get(mime, ".jpg")
    img = Image.open(io.BytesIO(raw))
    img.verify()                       # 파손 검증 (verify 후엔 재오픈 필요)
    img = Image.open(io.BytesIO(raw))

    is_animated_gif = mime == "image/gif" and getattr(img, "is_animated", False)

    if is_animated_gif:
        # 애니메이션 보존: 원본 바이트 그대로 저장
        path = dest_base.with_suffix(".gif")
        path.write_bytes(raw)
        w, h = img.size
    else:
        w, h = img.size
        long_edge = max(w, h)
        if long_edge > config.MAX_LONG_EDGE:
            scale = config.MAX_LONG_EDGE / long_edge
            img = img.resize((round(w * scale), round(h * scale)), Image.LANCZOS)
            w, h = img.size

        if ext in (".jpg", ".jpeg"):
            path = dest_base.with_suffix(".jpg")
            img.convert("RGB").save(path, "JPEG", quality=config.JPEG_QUALITY,
                                    optimize=True)
        elif ext == ".png":
            path = dest_base.with_suffix(".png")
            img.save(path, "PNG", optimize=True)
        elif ext == ".webp":
            path = dest_base.with_suffix(".webp")
            img.save(path, "WEBP", quality=config.JPEG_QUALITY)
        else:
            path = dest_base.with_suffix(ext)
            img.save(path)

    size_mb = round(path.stat().st_size / (1024 * 1024), 3)
    return path.name, w, h, size_mb


def main() -> int:
    print("== 스테이지 2: 이미지 다운로드 ==")
    config.WORKS_DIR.mkdir(parents=True, exist_ok=True)

    candidates = load_records(config.CANDIDATES_JSON)
    print(f"후보 {len(candidates)}개 다운로드 시작 → {config.WORKS_DIR}")

    ok: list[dict] = []
    fail = 0
    for i, rec in enumerate(candidates):
        local_id = f"{i:03d}"
        rec["local_id"] = local_id
        dest_base = config.WORKS_DIR / local_id
        try:
            raw = get_bytes(rec["image_src_url"])
            fname, w, h, mb = _save_image(raw, rec.get("mime") or "image/jpeg",
                                          dest_base)
            if max(w, h) < config.MIN_LONG_EDGE:
                print(f"  [{local_id}] 너무 작음 {w}x{h} — 제외")
                (config.WORKS_DIR / fname).unlink(missing_ok=True)
                fail += 1
                continue
            rec["image_file"] = fname
            rec["width"] = w
            rec["height"] = h
            rec["file_size_mb"] = mb
            ok.append(rec)
            if (i + 1) % 25 == 0:
                print(f"  ... {i + 1}/{len(candidates)} 처리")
        except Exception as e:  # noqa: BLE001
            print(f"  [{local_id}] 실패: {str(e)[:80]}")
            fail += 1

    save_records(config.DOWNLOADED_JSON, ok)
    total_mb = round(sum(r["file_size_mb"] for r in ok), 1)
    print(f"\n완료: 성공 {len(ok)}개 / 실패 {fail}개")
    print(f"총 이미지 용량: {total_mb} MB")
    print(f"저장: {config.DOWNLOADED_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
