#!/usr/bin/env python3
"""스테이지 5: 사람 검수용 review.html 생성.

described.json 의 각 레코드를 카드(썸네일 + 전체 메타 + 한글 설명)로 렌더링.
검수자는 각 카드에서 승인/거부를 토글하고(로컬 저장), 'decisions 내보내기'로
dataset/review_decisions.json 형태의 파일을 받아 6_build_manifest.py 에 반영할 수 있다.

실행:  python 5_build_review.py
결과:  dataset/review.html  (브라우저로 열기 — 이미지가 ../works/ 상대경로로 표시됨)
"""
from __future__ import annotations

import html
import json
import sys

import config
from lib.models import load_records


def _esc(v) -> str:
    return html.escape(str(v)) if v is not None else ""


def _card(r: dict) -> str:
    img = r.get("image_file") or ""
    status = r.get("review_status") or "pending"
    flagged = status == "needs_review"
    tags = " ".join(f"<span class='tag'>{_esc(t)}</span>" for t in (r.get("tags") or []))
    note = f"<div class='note'>⚠ {_esc(r['notes'])}</div>" if r.get("notes") else ""
    return f"""
<div class="card {'flagged' if flagged else ''}" data-id="{_esc(r['local_id'])}"
     data-status="{_esc(status)}">
  <div class="imgwrap"><img loading="lazy" src="../works/{_esc(img)}" alt=""></div>
  <div class="body">
    <div class="idrow"><b>#{_esc(r['local_id'])}</b>
      <span class="lic">{_esc(r.get('license'))}</span>
      <span class="st st-{_esc(status)}">{_esc(status)}</span></div>
    <div class="title">{_esc(r.get('title'))}</div>
    <div class="meta">{_esc(r.get('artist') or '작가 미상')} · {_esc(r.get('created_year') or '연도 미상')}</div>
    <div class="mat">{_esc(r.get('materials'))}</div>
    <div class="desc">{_esc(r.get('description_ko'))}</div>
    <details><summary>상세 설명</summary><p>{_esc(r.get('detail_text_ko'))}</p></details>
    <div class="tags">{tags}</div>
    {note}
    <div class="src"><a href="{_esc(r.get('source_page_url'))}" target="_blank">출처</a></div>
    <div class="actions">
      <button class="approve" onclick="setDecision('{_esc(r['local_id'])}','approved')">승인</button>
      <button class="reject" onclick="setDecision('{_esc(r['local_id'])}','rejected')">거부</button>
      <span class="decision"></span>
    </div>
  </div>
</div>"""


_TEMPLATE = """<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>키네틱 아트 데이터셋 검수 ({n}개)</title>
<style>
  body{{font-family:-apple-system,system-ui,sans-serif;margin:0;background:#f4f4f5;color:#18181b}}
  header{{position:sticky;top:0;background:#fff;border-bottom:1px solid #e4e4e7;padding:12px 20px;z-index:10;
    display:flex;gap:16px;align-items:center;flex-wrap:wrap}}
  header h1{{font-size:16px;margin:0}}
  .counts{{font-size:13px;color:#52525b}}
  button{{cursor:pointer;border:1px solid #d4d4d8;background:#fff;border-radius:6px;padding:6px 10px;font-size:13px}}
  #filter button.active{{background:#18181b;color:#fff}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px;padding:20px}}
  .card{{background:#fff;border:1px solid #e4e4e7;border-radius:10px;overflow:hidden;display:flex;flex-direction:column}}
  .card.flagged{{border-color:#f59e0b}}
  .imgwrap{{aspect-ratio:4/3;background:#fafafa;display:flex;align-items:center;justify-content:center;overflow:hidden}}
  .imgwrap img{{width:100%;height:100%;object-fit:contain}}
  .body{{padding:12px;display:flex;flex-direction:column;gap:6px}}
  .idrow{{display:flex;gap:8px;align-items:center;font-size:12px}}
  .lic{{color:#71717a}}
  .st{{margin-left:auto;padding:1px 6px;border-radius:4px;font-size:11px}}
  .st-auto_ok{{background:#dcfce7;color:#166534}} .st-needs_review{{background:#fef3c7;color:#92400e}}
  .title{{font-weight:600;font-size:14px}} .meta{{font-size:13px;color:#3f3f46}}
  .mat{{font-size:12px;color:#71717a}} .desc{{font-size:13px;line-height:1.5}}
  details summary{{font-size:12px;color:#2563eb;cursor:pointer}} details p{{font-size:12px;line-height:1.6;color:#3f3f46}}
  .tag{{display:inline-block;background:#f4f4f5;border:1px solid #e4e4e7;border-radius:4px;padding:1px 6px;font-size:11px;margin:1px}}
  .note{{background:#fffbeb;border:1px solid #fde68a;border-radius:6px;padding:6px;font-size:12px;color:#92400e}}
  .src a{{font-size:12px}}
  .actions{{display:flex;gap:8px;align-items:center;margin-top:4px}}
  .actions .approve{{border-color:#16a34a;color:#16a34a}} .actions .reject{{border-color:#dc2626;color:#dc2626}}
  .card.d-approved{{outline:2px solid #16a34a}} .card.d-rejected{{outline:2px solid #dc2626;opacity:.55}}
  .decision{{font-size:12px;font-weight:600}}
</style></head><body>
<header>
  <h1>키네틱 아트 데이터셋 검수</h1>
  <span class="counts" id="counts"></span>
  <span id="filter">
    <button data-f="all" class="active">전체</button>
    <button data-f="auto_ok">auto_ok</button>
    <button data-f="needs_review">needs_review</button>
    <button data-f="approved">승인됨</button>
    <button data-f="rejected">거부됨</button>
  </span>
  <button onclick="exportDecisions()" style="margin-left:auto;background:#18181b;color:#fff">decisions 내보내기</button>
  <button onclick="clearDecisions()">초기화</button>
</header>
<div class="grid" id="grid">{cards}</div>
<script>
const KEY="kinerag_review_decisions";
let D=JSON.parse(localStorage.getItem(KEY)||"{{}}");
function render(){{
  document.querySelectorAll(".card").forEach(c=>{{
    const id=c.dataset.id, d=D[id];
    c.classList.remove("d-approved","d-rejected");
    const span=c.querySelector(".decision"); span.textContent="";
    if(d){{c.classList.add("d-"+d); span.textContent=d==="approved"?"✔ 승인":"✘ 거부";}}
  }});
  const vals=Object.values(D);
  document.getElementById("counts").textContent=
    `총 {n}개 · 승인 ${{vals.filter(x=>x==='approved').length}} · 거부 ${{vals.filter(x=>x==='rejected').length}}`;
}}
function setDecision(id,v){{ D[id]=(D[id]===v?undefined:v); if(!D[id])delete D[id];
  localStorage.setItem(KEY,JSON.stringify(D)); render(); }}
function clearDecisions(){{ if(confirm("모든 결정을 지울까요?")){{D={{}};localStorage.setItem(KEY,"{{}}");render();}} }}
function exportDecisions(){{
  const blob=new Blob([JSON.stringify(D,null,2)],{{type:"application/json"}});
  const a=document.createElement("a"); a.href=URL.createObjectURL(blob);
  a.download="review_decisions.json"; a.click();
}}
document.querySelectorAll("#filter button").forEach(b=>b.onclick=()=>{{
  document.querySelectorAll("#filter button").forEach(x=>x.classList.remove("active"));
  b.classList.add("active"); const f=b.dataset.f;
  document.querySelectorAll(".card").forEach(c=>{{
    const st=c.dataset.status, d=D[c.dataset.id];
    let show=(f==="all")||(f===st)||(f===d);
    c.style.display=show?"":"none";
  }});
}});
render();
</script></body></html>"""


def main() -> int:
    if not config.DESCRIBED_JSON.exists():
        print(f"먼저 4_describe_ko.py ingest 로 {config.DESCRIBED_JSON} 를 만드세요.")
        return 1
    records = load_records(config.DESCRIBED_JSON)
    # 최종 manifest 에 포함된 것만 검수 대상으로 (있으면) — 제외된 Lumino/노이즈는 숨김
    if config.MANIFEST_JSON.exists():
        man_ids = {r["local_id"] for r in load_records(config.MANIFEST_JSON)}
        records = [r for r in records if r["local_id"] in man_ids]
        print(f"최종 선별 {len(man_ids)}개만 렌더링 (제외 항목 숨김)")
    described = [r for r in records if r.get("description_ko")]
    described.sort(key=lambda r: (r.get("review_status") != "needs_review",
                                  r.get("local_id")))
    cards = "\n".join(_card(r) for r in described)
    html_out = _TEMPLATE.format(n=len(described), cards=cards)
    config.REVIEW_HTML.write_text(html_out, encoding="utf-8")
    print(f"저장: {config.REVIEW_HTML}  ({len(described)}개 카드)")
    print(f"브라우저로 열어 검수 → 'decisions 내보내기' → dataset/review_decisions.json 저장")
    return 0


if __name__ == "__main__":
    sys.exit(main())
