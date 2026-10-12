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
from lib import imaging
from lib.http import get_bytes
from lib.models import load_records, save_records

SAVE_EVERY = 25   # 중간 저장 주기(이어받기용)

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
        img = imaging.fit_long_edge(img, config.MAX_LONG_EDGE)
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
    config.guard_first_batch(config.DOWNLOADED_JSON)

    candidates = load_records(config.CANDIDATES_JSON)

    # 이어받기(resume): 이 배치에서 이미 받은 것은 source_page_url 기준으로 재사용한다.
    # 중간 저장(SAVE_EVERY)과 합쳐, 중단돼도 받은 이미지·레코드를 잃지 않는다.
    ok: list[dict] = []
    done: dict[str, dict] = {}
    if config.DOWNLOADED_JSON.exists():
        ok = load_records(config.DOWNLOADED_JSON)
        done = {r.get("source_page_url"): r for r in ok}
        print(f"이어받기: 기존 {len(ok)}개 재사용")

    # local_id 발급: KINERAG_ID_START 지정 시 그 값, 아니면 기존 최대 id 기준 자동.
    # (works/·texts/·모든 배치 산출물·pinned 를 모두 보므로 라이브 id 와 충돌하지 않는다)
    if ok:
        next_id = max(int(r["local_id"]) for r in ok) + 1
        next_id = max(next_id, config.known_max_id() + 1)
    else:
        next_id = config.ID_START if config.ID_START_SET else config.auto_id_start()
    print(f"후보 {len(candidates)}개 → {config.WORKS_DIR} (신규 id {next_id:03d}부터)")

    fail = 0
    for i, rec in enumerate(candidates):
        if rec.get("source_page_url") in done:
            continue
        local_id = f"{next_id:03d}"
        dest_base = config.WORKS_DIR / local_id
        # works/ 는 라이브 파일서버 볼륨 — 기존 작품 이미지를 덮어쓰면 즉시 사고.
        existing = list(config.WORKS_DIR.glob(f"{local_id}.*"))
        if existing:
            save_records(config.DOWNLOADED_JSON, ok)
            print(f"  [{local_id}] 이미 존재({existing[0].name}) — 덮어쓰기 방지로 중단.\n"
                  f"  KINERAG_ID_START 를 지우고(자동 발급) 다시 실행하세요. (진행분 {len(ok)}개 저장됨)")
            return 1
        rec["local_id"] = local_id
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
            next_id += 1
            if len(ok) % SAVE_EVERY == 0:
                save_records(config.DOWNLOADED_JSON, ok)
                print(f"  ... {i + 1}/{len(candidates)} 처리 (중간 저장 {len(ok)}개)")
        except Exception as e:  # noqa: BLE001
            print(f"  [{local_id}] 실패: {str(e)[:80]}")
            fail += 1

    save_records(config.DOWNLOADED_JSON, ok)
    total_mb = round(sum(r["file_size_mb"] for r in ok), 1)
    print(f"\n완료: 성공 {len(ok)}개 / 실패 {fail}개")
    print(f"총 이미지 용량: {total_mb} MB")
    print(f"저장: {config.DOWNLOADED_JSON}")
    print("다음: 3_enrich.py → 2b_derivatives.py(썸네일·상세 파생본) → 4_describe_ko.py prepare")
    return 0


if __name__ == "__main__":
    sys.exit(main())
