-- 0075_pw_ambition.sql — the ambition (a big goal on Pathways) each item serves. Left empty, an item
-- serves the ambition its links lead to; a goal with none is an ambition itself, and a goal given one
-- is a step towards it. Lets Pathways colour, focus and arrange the map by ambition.
-- Run after 0010_pathways.sql. Safe to re-run.
alter table pw_node add column if not exists ambition_id uuid references pw_node on delete set null;
