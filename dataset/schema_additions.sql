-- kinetic_artworks 스키마 보강 (환경설치.md 기본 스키마에 추가)
-- 작가(검색 핵심) + 출처 표기 의무 + 영상 링크 반영. 1회 실행.
alter table kinetic_artworks add column if not exists artist text;
alter table kinetic_artworks add column if not exists video_url text;
alter table kinetic_artworks add column if not exists license text;
alter table kinetic_artworks add column if not exists attribution text;
alter table kinetic_artworks add column if not exists source_url text;
