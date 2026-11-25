-- 0073_note_order.sql — the comments on a to-do or meeting (kept in idea_note, 0044) in your own
-- order, by dragging. Until you drag them they go newest first, and a new one goes on top.
-- Run after 0044_idea_notes.sql. Safe to re-run.
alter table idea_note add column if not exists sort_order integer;
