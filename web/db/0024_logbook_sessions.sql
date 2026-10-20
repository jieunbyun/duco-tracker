-- 0024_logbook_sessions.sql — a logbook entry is a session: besides its notes
-- it remembers what it did to the project's action items (done, added,
-- updated, with their titles at the time) and the time it logged, if any, as
-- one time entry on the milestone. Actions never carry time.
alter table logbook_entry add column if not exists actions jsonb not null default '[]';
alter table logbook_entry add column if not exists time_entry_id uuid references time_entry on delete set null;
alter table logbook_entry add column if not exists time_minutes numeric check (time_minutes is null or time_minutes >= 0);

create or replace function keep_entry_history() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  new.author_id := old.author_id;
  new.created_at := old.created_at;
  if (old.project_id, old.planning_project_id, old.planning_milestone_id, old.group_milestone_id,
      old.entry_date, old.kind, old.did, old.results, old.next, old.links, old.actions, old.time_minutes)
     is distinct from (new.project_id, new.planning_project_id, new.planning_milestone_id, new.group_milestone_id,
      new.entry_date, new.kind, new.did, new.results, new.next, new.links, new.actions, new.time_minutes) then
    insert into logbook_revision (entry_id, editor_id, old_row) values (old.id, auth.uid(), to_jsonb(old));
    new.updated_at := now();
  end if;
  return new;
end $$;
