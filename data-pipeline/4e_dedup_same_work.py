"""4e단계: '같은 작품 다른 사진' 정리 (해시·URL 로 못 잡는 중복).

근거 두 가지를 합쳐 묶음(union-find)을 만들고, 묶음마다 해상도가 가장 큰 1장만 남긴다.
  ① 4단계 비전 판정 notes 의 '중복' 표기 + 그 안의 local_id
  ② (임베딩이 있으면) 한글 개념 텍스트 임베딩 코사인 ≥ --sim(기본 0.97) 이면서 같은 작가
나머지는 review_status='rejected' + notes 에 사유를 남긴다(삭제하지 않음 → 되돌리기 가능).
추가로 --exclude 로 준 local_id 는 사람 판단(민감 콘텐츠 등)으로 제외한다.

  ./.venv/bin/python 4e_dedup_same_work.py --dry-run
  ./.venv/bin/python 4e_dedup_same_work.py --exclude 1906,2818
"""
from __future__ import annotations

import argparse
import json
import re

import config
from lib.models import load_records, save_records

_ID_RE = re.compile(r"(?<![0-9A-Za-z.\-])(\d{3,4})(?![0-9A-Za-z.\-년])")  # 연도(1968년/1960s)·코드(AEC-002) 제외


# 한 작가가 같은 이름으로 여러 개체를 만든 '유형명' 제목 — 제목만으로 같은 작품이라 단정 불가
_GENERIC_TITLES = ("strandbeest", "스트란트비스트", "praxinoscope", "프락시노스코프",
                   "weather vane", "풍향계", "mobile", "모빌", "untitled", "무제",
                   "windspiel", "wind sculpture", "whirligig", "wind chime", "kinetic sculpture",
                   "kinetische", "light painting", "camera painting")


def _orig(s: str | None) -> str:
    """'한글 (Original)' → 'original' 정규화(관사·숫자 접미·구두점 제거). 괄호 없으면 전체."""
    if not s:
        return ""
    m = re.findall(r"\(([^()]+)\)", s)
    t = (m[0] if m else s).lower()           # 첫 괄호 = 원어 제목(뒤 괄호는 작가명일 수 있음)
    t = re.sub(r"^(the|a|an|le|la|les|der|die|das)\s+", "", t)
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+\d+$", "", t.strip())      # '... 2' 같은 사진 연번
    return re.sub(r"\s+", " ", t).strip()


def _ok(r: dict) -> bool:
    return bool(r.get("description_ko")) and r.get("review_status") != "rejected"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--sim", type=float, default=0.97)
    ap.add_argument("--exclude", default="")
    ap.add_argument("--force-pinned", action="store_true",
                    help="라이브(pinned) 작품도 중복이면 제외(기본: 보호하고 리포트만)")
    ap.add_argument("--group", default="", help="사람이 묶을 id 목록: '1,2,3;7,8'")
    a = ap.parse_args()

    files = config.all_described_files()
    data = {p: load_records(p) for p in files}
    recs = {str(r["local_id"]): r for rs in data.values() for r in rs if _ok(r)}
    pinned = set()
    pl = config.DATASET_DIR / "pinned_live.json"
    if pl.exists():
        pinned = {str(x) for x in json.loads(pl.read_text(encoding="utf-8"))}

    parent = {k: k for k in recs}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: str, y: str) -> None:
        if x in parent and y in parent:
            parent[find(x)] = find(y)

    # ① notes 의 중복 표기. 1800~2030 은 연도일 수 있으므로 '중복후보:' 목록 안이거나
    #    바로 뒤에 '와/과' 가 붙은 경우만 id 로 인정한다.
    note_pairs = []
    for lid, r in recs.items():
        n = r.get("notes") or ""
        if "중복" not in n:
            continue
        listed = set()
        for seg in re.findall(r"중복\s*후보\s*[:：]\s*([0-9,\s/·및]+)", n):
            listed.update(re.findall(r"\d{3,4}", seg))
        for m in _ID_RE.finditer(n):
            other = m.group(1)
            if other == lid or other not in recs:
                continue
            yearish = 1800 <= int(other) <= 2030
            particle = n[m.end():m.end() + 1] in ("와", "과")
            if yearish and other not in listed and not particle:
                continue
            union(lid, other)
            note_pairs.append((lid, other))

    # ② 임베딩 유사도 + 같은 작가(작가 미상끼리는 묶지 않음 — 서로 다른 작품 오병합 방지)
    emb = [(k, r["embedding"], _orig(r.get("artist")))
           for k, r in recs.items() if r.get("embedding")]
    sim_pairs = 0
    for i in range(len(emb)):
        ki, vi, ai = emb[i]
        if not ai:
            continue
        for j in range(i + 1, len(emb)):
            kj, vj, aj = emb[j]
            if ai != aj:
                continue
            if sum(x * y for x, y in zip(vi, vj)) >= a.sim:   # e5 임베딩은 정규화됨
                union(ki, kj)
                sim_pairs += 1

    # ③ 같은 작가(확정) + 같은 한글 제목 → 같은 작품. 단 유형명 제목(스트란트비스트 등)은
    #    한 작가의 서로 다른 개체를 가리키므로 제외. --group 으로 사람이 직접 묶을 수도 있다.
    # (a) 작가 확정끼리: 원어 작가+원어 제목 일치
    # (b) 작가 미상 레코드: 제목이 고유(3단어+)하고 그 제목을 쓰는 확정 작가가 0~1명일 때만 연결
    #     (서로 다른 작가가 같은 제목을 쓰는 경우 — 예: 공동 연작 — 는 묶지 않는다)
    by_key: dict[str, str] = {}
    by_title: dict[str, list[str]] = {}
    title_artists: dict[str, set[str]] = {}
    for k, r in recs.items():
        title = _orig(r.get("title"))
        artist = _orig(r.get("artist"))
        if not title or any(g in title for g in _GENERIC_TITLES):
            continue
        by_title.setdefault(title, []).append(k)
        if artist:
            title_artists.setdefault(title, set()).add(artist)
            key = artist + "|" + title
            if key in by_key:
                union(k, by_key[key])
            else:
                by_key[key] = k
    for title, ks in by_title.items():
        if len(title.split()) < 3 or len(title_artists.get(title, ())) > 1:
            continue
        unknown = [k for k in ks if not _orig(recs[k].get("artist"))]
        if unknown:
            for k in ks:
                if k != unknown[0]:
                    union(unknown[0], k)
    for grp in filter(None, (g.strip() for g in a.group.split(";"))):
        ids = [x.strip() for x in grp.split(",") if x.strip()]
        for x in ids[1:]:
            union(ids[0], x)

    groups: dict[str, list[str]] = {}
    for k in recs:
        groups.setdefault(find(k), []).append(k)

    excluded = {k for k in (s.strip() for s in a.exclude.split(",")) if k in recs}
    drop: dict[str, str] = {k: "[4e 제외: 사람 판단(민감/부적합)]" for k in excluded}
    held: list[list[str]] = []
    for g in groups.values():
        if len(g) < 2:
            continue
        cand = [k for k in g if k not in excluded] or g
        # 이미 라이브인 것 우선 유지(링크 안정성) → 그다음 해상도
        keep = max(cand, key=lambda k: (k in pinned,
                                        (recs[k].get("width") or 0) * (recs[k].get("height") or 0)))
        live_others = [k for k in cand if k != keep and k in pinned]
        if live_others and not a.force_pinned:
            held.append(sorted(g))      # 라이브 작품 삭제는 사람 확인 후(--force-pinned)
        for k in cand:
            if k == keep or (k in pinned and not a.force_pinned):
                continue
            drop[k] = f"[4e 중복정리: {keep} 와 같은 작품]"

    multi = [g for g in groups.values() if len(g) > 1]
    print(f"유효 {len(recs)} / 중복 묶음 {len(multi)} (임베딩 쌍 {sim_pairs}) / 제외 {len(drop)}")
    for g in (multi if a.dry_run else multi[:15]):
        print("  묶음:", sorted(g))
    if a.dry_run:
        for x, y in note_pairs:
            print(f"  notes 근거: {x} → {y}")
    for g in held:
        print("  ⚠ 라이브 작품 여러 개가 같은 묶음(보호됨, 확인 후 --force-pinned):", g)
    if a.dry_run:
        return 0

    for p, rs in data.items():
        changed = False
        for r in rs:
            why = drop.get(str(r["local_id"]))
            if why and _ok(r):
                r["review_status"] = "rejected"
                r["notes"] = ((r.get("notes") or "") + " " + why).strip()
                changed = True
        if changed:
            save_records(p, rs)
    print(f"적용: {len(drop)}건 rejected 처리 → 남은 유효 {len(recs) - len(drop)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
