-- 0066_tidy_kind.sql — a small task can be ticked as a tidy-up (and is coloured so in Week).
-- Safe to re-run.
alter table tidy add column if not exists is_tidy boolean not null default false;
