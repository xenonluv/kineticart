# 키네틱 아트 원천 데이터 파일서버 (nginx)
# 로컬(집 Mac)에서 실행하다가, 동일 이미지를 그대로 AWS 등으로 이전 가능.
FROM nginx:alpine

# 파일서버 설정 (works/·texts/ 정적 서빙 + CORS)
COPY file-server/default.conf /etc/nginx/conf.d/default.conf

# --- 이식용 immutable 이미지 ------------------------------------------------
# 아래 두 줄의 주석을 해제하면 이미지·텍스트 파일까지 이미지 안에 포함되어
# 볼륨 마운트 없이 어디서든 단독 실행 가능한 자체완결 이미지가 된다.
# (이 경우 docker-compose 의 build.context 가 리포 루트여야 함 — 이미 그렇게 설정됨)
# COPY works /srv/works
# COPY texts /srv/texts
# ---------------------------------------------------------------------------

EXPOSE 8787
