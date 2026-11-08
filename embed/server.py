"""kinerag-embed: 한글 텍스트 → e5 질의 임베딩 → 갤러리 작품(manifest) 유사도 검색.

갤러리 작품 벡터는 data-pipeline 5b_embed.py 가 만든 'passage:' 임베딩(manifest.json)을 그대로 쓴다.
같은 모델(intfloat/multilingual-e5-large)로 질의만 'query:' 접두를 붙여 임베딩해야 정확하다.
내부 네트워크 전용(포트 비공개). 외부 의존 최소화를 위해 표준 http.server 사용.

  POST /similar {"text": "...", "k": 8}  → {"results": [{"image_url": ..., "score": 0.83}, ...]}
  GET  /health                          → {"ok": true, "items": 738}
"""
from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
from fastembed import TextEmbedding

MODEL_NAME = "intfloat/multilingual-e5-large"
MANIFEST = os.environ.get("MANIFEST_PATH", "/data/manifest.json")
MAX_TEXT = 2000
E5_QUERY_PREFIX = "query: "  # fastembed 는 접두를 자동으로 붙이지 않는다(문서는 5b 가 "passage: ")
MAX_BODY = 64 * 1024

_lock = threading.Lock()
_model = TextEmbedding(model_name=MODEL_NAME, cache_dir=os.environ.get("FASTEMBED_CACHE", "/models"))
_index: dict = {"mtime": None, "urls": [], "mat": np.zeros((0, 1024), dtype=np.float32)}


def _load_index() -> None:
    """manifest 가 바뀌면(시드 갱신) 다시 읽는다 — 컨테이너 재시작 없이 반영.
    (manifest 는 os.replace 로 교체되므로 파일이 아닌 dataset/ 디렉터리를 마운트해야 새 inode 가 보인다)"""
    mtime = os.path.getmtime(MANIFEST)
    if _index["mtime"] == mtime:
        return
    rows = json.load(open(MANIFEST, encoding="utf-8"))
    urls, vecs = [], []
    for r in rows:
        e = r.get("embedding")
        if r.get("image_url") and e and len(e) == 1024:
            urls.append(r["image_url"])
            vecs.append(e)
    mat = np.asarray(vecs, dtype=np.float32).reshape(-1, 1024)
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    mat = mat / np.where(norms == 0, 1, norms)
    _index.update(mtime=mtime, urls=urls, mat=mat)


def similar(text: str, k: int) -> list[dict]:
    with _lock:  # 인덱스 교체만 직렬화 — 추론(onnxruntime 세션)은 스레드 안전하므로 lock 밖
        _load_index()
        urls, mat = _index["urls"], _index["mat"]
    q = np.asarray(next(iter(_model.embed([E5_QUERY_PREFIX + text[:MAX_TEXT]]))), dtype=np.float32)
    if not urls:
        return []
    q /= np.linalg.norm(q) or 1.0
    scores = mat @ q
    top = np.argsort(-scores)[:k]
    return [{"image_url": urls[i], "score": round(float(scores[i]), 4)} for i in top]


class Handler(BaseHTTPRequestHandler):
    timeout = 15  # 본문 길이 위조 등으로 스레드가 무기한 대기하지 않도록
    def _send(self, code: int, obj: dict) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        if self.path == "/health":
            with _lock:
                _load_index()
                n = len(_index["urls"])
            return self._send(200, {"ok": True, "items": n})
        self._send(404, {"error": "not found"})

    def do_POST(self):  # noqa: N802
        if self.path != "/similar":
            return self._send(404, {"error": "not found"})
        try:
            n = int(self.headers.get("content-length") or 0)
            if n <= 0 or n > MAX_BODY:
                return self._send(413, {"error": "bad body size"})
            req = json.loads(self.rfile.read(n))
            text = str(req.get("text") or "").strip()
            k = max(1, min(int(req.get("k") or 8), 24))
        except (ValueError, TypeError, AttributeError):
            return self._send(400, {"error": "bad request"})
        if not text:
            return self._send(400, {"error": "empty text"})
        try:
            self._send(200, {"results": similar(text, k)})
        except Exception as e:  # noqa: BLE001
            self._send(500, {"error": str(e)[:200]})

    def log_message(self, fmt, *args):  # 요청 로그 축소
        pass


if __name__ == "__main__":
    _load_index()
    print(f"embed ready: {len(_index['urls'])} items", flush=True)
    ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
