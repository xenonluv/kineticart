#!/usr/bin/env python3
"""스테이지 2b: 웹 표시용 파생 이미지 생성 (원본 works/ 는 그대로 둔다).

  cards/NNN.webp   : 장변 CARD_LONG_EDGE(480) 정지 WebP — 갤러리 카드·채팅 참조 칩(DB thumbnail_url)
  thumbs/NNN.webp  : 장변 THUMB_LONG_EDGE(768) 정지 WebP — Haiku 비전 입력·이미지 생성 참조
  display/NNN.webp : 장변 DISPLAY_LONG_EDGE(1600) WebP — 상세 화면
                     애니메이션 GIF 는 애니메이션 WebP(장변 DISPLAY_ANIM_LONG_EDGE)로 움직임 보존

원본(장변 2000, GIF 최대 54MB)을 그리드에 그대로 쓰면 첫 화면이 수십 MB 가 되어
집 Mac 업로드 회선·터널이 병목이 된다. 파생본은 파일 크기를 1/10 수준으로 줄인다.

대상: 모든 배치 enriched*.json·described*.json 에서 선별(selected)됐거나 설명이 있는 레코드.
      → 새 배치는 3_enrich.py 직후(4단계 prepare 전)에 실행한다. --all 이면 works/ 전체.
멱등: 파생본이 원본보다 새로우면 건너뛴다(--force 로 재생성).

실행:  python 2b_derivatives.py [--all] [--force]
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

import config
from lib import imaging
from lib.models import load_records


def _targets(all_works: bool) -> list[Path]:
    if all_works:
        return sorted(p for p in config.WORKS_DIR.iterdir() if p.is_file()
                      and not p.name.startswith("."))
    names: set[str] = set()
    sources = sorted(config.DATASET_DIR.glob("enriched*.json")) + config.all_described_files()
    for path in sources:
        for r in load_records(path):
            # 선별(설명 생성 대상)이거나 이미 설명이 있는 것만 — 미선별 후보까지 만들 필요는 없다
            if r.get("image_file") and (r.get("selected") or r.get("description_ko")):
                names.add(r["image_file"])
    return sorted(config.WORKS_DIR / n for n in names)


def _fresh(dest: Path, src: Path) -> bool:
    return dest.exists() and dest.stat().st_mtime >= src.stat().st_mtime


def main() -> int:
    all_works = "--all" in sys.argv
    force = "--force" in sys.argv
    for d in (config.CARDS_DIR, config.THUMBS_DIR, config.DISPLAY_DIR):
        d.mkdir(parents=True, exist_ok=True)

    targets = _targets(all_works)
    print(f"== 스테이지 2b: 파생 이미지 == 대상 {len(targets)}개")
    made = skipped = missing = failed = 0
    src_bytes = card_bytes = thumb_bytes = disp_bytes = 0

    for i, src in enumerate(targets, 1):
        if not src.exists():
            missing += 1
            print(f"  [누락] {src.name}")
            continue
        stem = src.stem
        card = config.CARDS_DIR / f"{stem}.webp"
        thumb = config.THUMBS_DIR / f"{stem}.webp"
        disp = config.DISPLAY_DIR / f"{stem}.webp"
        if not force and all(_fresh(d, src) for d in (card, thumb, disp)):
            skipped += 1
        else:
            try:
                with Image.open(src) as img:
                    img.load()
                    imaging.save_static_webp(img, card, config.CARD_LONG_EDGE,
                                             config.CARD_QUALITY)
                    imaging.save_static_webp(img, thumb, config.THUMB_LONG_EDGE,
                                             config.THUMB_QUALITY)
                    if imaging.is_animated(img):
                        imaging.save_animated_webp(img, disp, config.DISPLAY_ANIM_LONG_EDGE,
                                                   config.DISPLAY_ANIM_QUALITY)
                    else:
                        imaging.save_static_webp(img, disp, config.DISPLAY_LONG_EDGE,
                                                 config.DISPLAY_QUALITY)
                made += 1
            except Exception as e:  # noqa: BLE001 — 한 장 실패가 전체를 멈추지 않게
                failed += 1
                for d in (card, thumb, disp):
                    d.unlink(missing_ok=True)
                print(f"  [실패] {src.name}: {str(e)[:100]}")
                continue
        src_bytes += src.stat().st_size
        card_bytes += card.stat().st_size
        thumb_bytes += thumb.stat().st_size
        disp_bytes += disp.stat().st_size
        if i % 50 == 0:
            print(f"  ... {i}/{len(targets)}")

    mb = lambda b: f"{b / 1e6:.1f}MB"
    print(f"\n생성 {made} / 건너뜀 {skipped} / 원본누락 {missing} / 실패 {failed}")
    print(f"용량: 원본 {mb(src_bytes)} → 카드 {mb(card_bytes)} · 썸네일 {mb(thumb_bytes)} · "
          f"상세 {mb(disp_bytes)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
