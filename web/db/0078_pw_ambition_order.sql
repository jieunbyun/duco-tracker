-- 0078_pw_ambition_order.sql — the ambitions on Pathways in your own order, by dragging their
-- headings with rows by ambition (also the order of their names above the map). Until you drag
-- them they go as they sit in the goals column. Run after 0075_pw_ambition.sql. Safe to re-run.
alter table pw_node add column if not exists ambition_order integer;
