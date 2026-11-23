-- 0064_meeting_agenda.sql — a meeting can be planned ahead: its agenda is kept with its
-- sections ("Agenda", one item a line, ticked off on the day), and it can be tied to its
-- entry on the Week calendar, so each leads to the other. Safe to re-run.
alter table meeting add column if not exists todo_id uuid references todo on delete set null;
create index if not exists meeting_todo on meeting (todo_id) where todo_id is not null;
