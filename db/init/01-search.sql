-- 스케일(수천 개) 대비 검색 인프라.
-- 최초 기동 시 자동 적용되며, 실행중 DB에는 psql 로 1회 수동 적용한다.

-- 퍼지 검색(제목/작가/설명 부분일치)을 인덱스로 고속화
create extension if not exists pg_trgm;
create index if not exists idx_artwork_title_trgm  on kinetic_artworks using gin (title gin_trgm_ops);
create index if not exists idx_artwork_artist_trgm on kinetic_artworks using gin (artist gin_trgm_ops);
create index if not exists idx_artwork_desc_trgm   on kinetic_artworks using gin (description gin_trgm_ops);

-- 패싯(필터 카운트) 뷰 — 태그/작가/연대별 개수
create or replace view tag_facets as
  select unnest(tags) as tag, count(*) as count
  from kinetic_artworks
  group by 1
  order by count desc, tag;

create or replace view artist_facets as
  select artist, count(*) as count
  from kinetic_artworks
  where artist is not null
  group by 1
  order by count desc, artist;

create or replace view decade_facets as
  select (created_year / 10 * 10) as decade, count(*) as count
  from kinetic_artworks
  where created_year is not null
  group by 1
  order by decade desc;

grant select on tag_facets, artist_facets, decade_facets to web_anon;
