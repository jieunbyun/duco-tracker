-- 0009_ideas.sql — "To think about": ideas jotted down as they come (conference
-- titles, angles to explore…). Kept as to-dos of kind 'idea': not tied to a
-- week, never counted as planned time, listed until done or turned into a to-do.
alter table todo drop constraint if exists todo_kind_check;
alter table todo add constraint todo_kind_check check (kind in ('task', 'meeting', 'idea'));
