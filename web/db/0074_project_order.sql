-- 0074_project_order.sql — your projects in your own order within each category on Planning,
-- by dragging. Until you drag them they go important (★) first, then by end date, and a new
-- one goes on top. Safe to re-run.
alter table project add column if not exists sort_order integer;
