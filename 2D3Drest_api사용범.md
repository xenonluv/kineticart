# 2D·3D 생성물 REST API 사용법

AI로 생성한 2D 이미지와 3D 모델(GLB)을 외부 프로그램에서 조회하고 내려받는 API입니다.
**조회와 다운로드만 가능**하며, 호출해도 이미지·3D 생성 비용은 발생하지 않습니다.

- 기본 주소: `https://www.kctikinec.cloud/api/v1`
- 응답 형식: JSON (파일 다운로드 제외)
- 시각 형식: ISO-8601 UTC (예: `2026-11-08T17:01:07.311Z`)

## 1. 인증

모든 요청에 API 키를 헤더로 보냅니다. 키는 서버 `.env`의 `API_V1_KEY` 값이며, 받는 쪽에 안전한 경로로 전달하세요.

```
Authorization: Bearer <API_KEY>
```

키가 없거나 틀리면 `401`이 반환됩니다. 키는 소스 코드나 URL에 넣지 말고, 유출되면 `.env` 값을 바꾼 뒤 `docker compose up -d web`으로 교체하세요.

## 2. 엔드포인트

| 메서드 | 경로 | 용도 |
|---|---|---|
| GET | `/generations` | 생성물 목록 |
| GET | `/generations/{id}` | 한 건의 상세 정보 |
| GET | `/generations/{id}/image` | 2D 이미지 파일 받기 |
| GET | `/generations/{id}/model` | 3D 모델(GLB) 파일 받기 |

`id`를 미리 알 필요는 없습니다. 목록 응답의 `id`와 파일 주소(`image.url`, `model.url`)를 그대로 쓰면 됩니다.

### 목록 파라미터

| 파라미터 | 설명 | 기본값 |
|---|---|---|
| `type` | `2d`: 이미지가 있는 항목 / `3d`: GLB가 완성된 항목 | 전체 |
| `since` | 이 시각 이후에 변경된 항목만. 시간대 필수 | 없음 |
| `after_id` | `since`와 함께 사용. 같은 시각 항목 중 이 `id` 다음부터 이어받기 | 없음 |
| `page` | 페이지 번호(1부터). `since`와 함께 쓸 수 없음 | 1 |
| `limit` | 페이지당 개수(1~100) | 20 |

**정렬:** `since`가 없으면 최근 변경순, 있으면 **오래된 변경부터** 반환합니다. `since`를 쓰면 안정화를 위해 **최근 5초 안에 바뀐 항목은 다음 호출에 나옵니다.**

### 목록 응답

```json
{
  "items": [
    {
      "id": "1794157156145-7ac3550c",
      "created_at": "2026-11-08T16:59:16.145Z",
      "updated_at": "2026-11-08T17:01:07.311Z",
      "image": {
        "url": "https://www.kctikinec.cloud/api/v1/generations/1794157156145-7ac3550c/image",
        "mime": "image/png",
        "bytes": 2235500
      },
      "model": {
        "status": "success",
        "progress": 100,
        "url": "https://www.kctikinec.cloud/api/v1/generations/1794157156145-7ac3550c/model",
        "format": "glb",
        "bytes": 4049824
      },
      "expires_at": "2026-12-08T16:59:16.151Z"
    }
  ],
  "page": 1,
  "limit": 20,
  "total": 11,
  "has_more": false
}
```

상세 조회(`/generations/{id}`)는 `items`의 항목 하나와 같은 형식을 반환합니다.

### 필드 설명

| 필드 | 설명 |
|---|---|
| `id` | 생성물 고유 번호. 2D와 3D가 같은 `id`를 공유 |
| `created_at` | 이미지 생성 시각 |
| `updated_at` | 마지막 변경 시각. 3D 진행·완성 시 바뀜 |
| `image` | 2D 이미지 정보. 파일이 삭제됐으면 `null` |
| `model.status` | 아래 표 참조 |
| `model.progress` | 3D 진행률(0~100) |
| `model.url`, `format`, `bytes` | `status`가 `success`일 때만 값이 있고 그 외에는 `null` |
| `expires_at` | 이 항목에서 **가장 먼저 삭제될 파일**의 예정 시각. 자동 삭제가 꺼져 있으면 `null` |

| `model.status` | 의미 |
|---|---|
| `none` | 3D를 만든 적이 없거나 파일이 삭제됨 |
| `queued` | 3D 대기 중 |
| `running` | 3D 생성 중 |
| `success` | 완성, `model.url`로 다운로드 가능 |
| `failed` | 3D 생성 실패, 또는 24시간 넘게 완성되지 않음(드물게 나중에 `success`로 바뀔 수 있음) |

## 3. 새 생성물만 받는 방법(권장)

**`page`를 넘기는 방식으로 동기화하지 마세요.** 진행 중 항목이 바뀌면 순서가 밀려 일부를 놓칠 수 있습니다. 항상 `since`와 `after_id`로 이어받습니다.

1. 처음에는 `since=1970-01-01T00:00:00Z`로 호출합니다.
2. 응답의 **마지막 항목**의 `updated_at`을 `since`, `id`를 `after_id`로 저장합니다.
3. `has_more`가 `true`면 그 값으로 바로 다시 호출합니다.
4. `false`면 저장한 값을 보관하고, **1분 이상** 뒤 같은 값으로 호출합니다. 결과가 비어 있으면 저장값은 그대로 둡니다.
5. 항목은 `id`로 구분해 저장합니다. 3D는 이미지보다 늦게 끝나므로, 같은 `id`가 `none`·`running`으로 왔다가 나중에 `success`로 다시 오는 것은 정상입니다.

## 4. 파일 받기

- 파일 주소도 **같은 인증 헤더가 필요**합니다.
- 응답은 `attachment`로 내려가며, 이미지는 `image/png`·`image/jpeg`·`image/webp`, 3D는 `model/gltf-binary`입니다.
- 파일이 아직 없거나 삭제됐으면 `404`입니다.

## 5. 보관 기간

생성물은 기본 **30일 뒤 자동 삭제**됩니다(삭제 작업은 6시간마다 실행). `expires_at` 전에 내려받아 보관하세요. 삭제된 항목은 목록에서 사라지며, 삭제 알림은 따로 보내지 않습니다.

## 6. 오류

오류 응답은 `{"error": "메시지"}` 형식입니다.

| 코드 | 의미 |
|---|---|
| 400 | `type`, `since`, `after_id`, `page`, `limit` 값이 잘못됨 |
| 401 | API 키 없음 또는 틀림 |
| 404 | 생성물 또는 파일 없음 |
| 500 | 서버 오류. 잠시 후 재시도 |

## 7. 예제

### curl

```bash
export API_KEY='발급받은 키'
BASE=https://www.kctikinec.cloud/api/v1

# 목록
curl -H "Authorization: Bearer $API_KEY" "$BASE/generations?limit=10"

# 3D 완성 항목만
curl -H "Authorization: Bearer $API_KEY" "$BASE/generations?type=3d"

# 특정 시각 이후 변경분(이어받기는 3장 참조)
curl -H "Authorization: Bearer $API_KEY" "$BASE/generations?since=2026-11-09T00:00:00Z"

# GLB 다운로드
curl -H "Authorization: Bearer $API_KEY" -o model.glb "$BASE/generations/<id>/model"
```

### Python (새 생성물 동기화)

```python
import json
import os
from pathlib import Path
import requests

BASE = "https://www.kctikinec.cloud/api/v1"
HEADERS = {"Authorization": f"Bearer {os.environ['API_KEY']}"}
OUT = Path("downloads")
OUT.mkdir(exist_ok=True)
CURSOR = Path("cursor.json")


def download(url: str, path: Path) -> None:
    if path.exists():
        return
    tmp = path.with_suffix(path.suffix + ".part")
    with requests.get(url, headers=HEADERS, stream=True, timeout=120) as r:
        if r.status_code == 404:  # 보관 기간이 지나 삭제됨
            return
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    tmp.rename(path)


def sync() -> None:
    cur = json.loads(CURSOR.read_text()) if CURSOR.exists() else {"since": "1970-01-01T00:00:00Z"}
    while True:
        r = requests.get(f"{BASE}/generations", headers=HEADERS, params={**cur, "limit": 100}, timeout=30)
        r.raise_for_status()
        data = r.json()
        for it in data["items"]:
            if it["image"]:
                ext = it["image"]["mime"].split("/")[1].replace("jpeg", "jpg")
                download(it["image"]["url"], OUT / f"{it['id']}.{ext}")
            if it["model"]["status"] == "success":
                download(it["model"]["url"], OUT / f"{it['id']}.glb")
        if data["items"]:  # 페이지를 다 받은 뒤에만 저장(중간 실패 시 다시 받음)
            last = data["items"][-1]
            cur = {"since": last["updated_at"], "after_id": last["id"]}
            CURSOR.write_text(json.dumps(cur))
        if not data["has_more"]:
            break


if __name__ == "__main__":
    sync()
```
