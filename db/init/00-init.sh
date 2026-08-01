#!/bin/bash
# Postgres 최초 기동 시 1회 실행 (데이터 볼륨이 비어있을 때).
#   - kinetic_artworks 테이블(전 컬럼) + 공개읽기 RLS
#   - PostgREST 역할: web_anon(익명 읽기전용), authenticator(PostgREST 접속용)
#   - dataset/seed.sql (69행) 적재
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<EOSQL
create extension if not exists pgcrypto;

create table kinetic_artworks (
  id              uuid primary key default gen_random_uuid(),
  title           text not null,
  artist          text,
  description     text,
  created_year    int,
  materials       text,
  dimensions      text,
  tags            text[],
  thumbnail_url   text,
  image_url       text not null,
  detail_text_url text,
  video_url       text,
  file_size_mb    numeric,
  license         text,
  attribution     text,
  source_url      text,
  created_at      timestamptz default now(),
  updated_at      timestamptz default now()
);

-- 검색용 인덱스
create index on kinetic_artworks using gin (tags);
create index on kinetic_artworks (artist);
create index on kinetic_artworks (created_year);

-- 공개 읽기 전용 (외부/LLM 조회)
alter table kinetic_artworks enable row level security;
create policy "public read" on kinetic_artworks for select using (true);

-- PostgREST 역할
create role web_anon nologin;
grant usage on schema public to web_anon;
grant select on kinetic_artworks to web_anon;

create role authenticator noinherit login password '${AUTHENTICATOR_PASSWORD}';
grant web_anon to authenticator;
EOSQL

# 시드 데이터 (69행) — 파일은 compose 로 /seed/seed.sql 에 마운트됨
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -f /seed/seed.sql

echo "kinetic_artworks 초기화 완료: $(psql -tAc 'select count(*) from kinetic_artworks' --username "$POSTGRES_USER" --dbname "$POSTGRES_DB") 행"
