-- 0022_logbook_planning.sql — one logbook for every project: an entry can be
-- about a shared project or one of your own Planning projects, and about one of
-- that project's existing milestones. A note on a Planning project can only be
-- written by that project's owner, and like any entry it is seen only by its
-- author (and the supervisor, who is you).
alter table logbook_entry add column if not exists planning_project_id uuid references project on delete set null;
alter table logbook_entry add column if not exists planning_milestone_id uuid references milestone on delete set null;
alter table logbook_entry add column if not exists group_milestone_id uuid references group_milestone on delete set null;
create index if not exists logbook_entry_planning_idx on logbook_entry (planning_project_id, entry_date);

-- what an entry may be about: a project you are on (or any, as supervisor), a
-- Planning project of your own, and a milestone belonging to that project
create function logbook_entry_allowed(e logbook_entry) returns boolean
language sql stable set search_path = public as $$
  select (e.project_id is null or is_on_project(e.project_id) or is_supervisor())
     and (e.planning_project_id is null
          or exists (select 1 from project p where p.id = e.planning_project_id and p.user_id = auth.uid()))
     and (e.planning_milestone_id is null
          or exists (select 1 from milestone m where m.id = e.planning_milestone_id and m.project_id = e.planning_project_id))
     and (e.group_milestone_id is null
          or exists (select 1 from group_milestone g where g.id = e.group_milestone_id and g.project_id = e.project_id))
$$;

drop policy if exists add on logbook_entry;
drop policy if exists change on logbook_entry;
create policy add on logbook_entry for insert to authenticated
  with check (author_id = auth.uid() and is_group_member() and logbook_entry_allowed(logbook_entry));
create policy change on logbook_entry for update to authenticated using (author_id = auth.uid())
  with check (author_id = auth.uid() and logbook_entry_allowed(logbook_entry));

-- moving an entry to another project or milestone is an edit like any other
create or replace function keep_entry_history() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  new.author_id := old.author_id;
  new.created_at := old.created_at;
  if (old.project_id, old.planning_project_id, old.planning_milestone_id, old.group_milestone_id,
      old.entry_date, old.kind, old.did, old.results, old.next, old.links)
     is distinct from (new.project_id, new.planning_project_id, new.planning_milestone_id, new.group_milestone_id,
      new.entry_date, new.kind, new.did, new.results, new.next, new.links) then
    insert into logbook_revision (entry_id, editor_id, old_row) values (old.id, auth.uid(), to_jsonb(old));
    new.updated_at := now();
  end if;
  return new;
end $$;
