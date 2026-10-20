-- 0023_logbook_actions.sql — action items in the Logbook are to-dos: one list.
-- An action item added in the Logbook is a to-do on your Week list too, and
-- ticking it in either place ticks both. A to-do can now belong to a shared
-- project (as well as a Planning one) and carry links (files on OneDrive).
-- To-dos stay their owner's alone; a member's action items reach you only
-- through member_actions_for(), read-only.
alter table todo add column if not exists group_project_id uuid references group_project on delete set null;
alter table todo add column if not exists links text[] not null default '{}';
create index if not exists todo_group_project_idx on todo (group_project_id) where group_project_id is not null;

-- a to-do can only belong to a shared project its owner is on (or any, for you)
create policy shared_project_ok on todo as restrictive for all to authenticated
  using (true)
  with check (group_project_id is null or is_on_project(group_project_id) or is_supervisor());

-- a member's action items (their to-dos on shared projects), for you to read
create function member_actions_for(p uuid) returns table (
  id uuid, title text, note text, links text[], group_project_id uuid, is_done boolean, done_at timestamptz,
  due_on date, created_at timestamptz
)
language sql stable security definer set search_path = public as $$
  select t.id, t.title, t.note, t.links, t.group_project_id, t.is_done, t.done_at, t.due_on, t.created_at
  from todo t
  where t.user_id = p and t.group_project_id is not null and not t.is_cancelled and t.kind = 'task'
    and (p = auth.uid() or is_supervisor())
  order by t.is_done, t.created_at
$$;
