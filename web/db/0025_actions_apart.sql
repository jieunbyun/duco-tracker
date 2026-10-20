-- 0025_actions_apart.sql — action items are not to-dos: they are a project's
-- internal notes on what to do next, kept in the Logbook and never on Week's
-- lists. They live in the same table with a kind of their own ('action'), so
-- they keep their comments, links and sessions.
alter table todo drop constraint if exists todo_kind_check;
alter table todo add constraint todo_kind_check check (kind in ('task', 'meeting', 'idea', 'action'));

-- the action items already made in the Logbook: those a session recorded as
-- added, and those made since action items began (2026-10-20) that look like
-- one — on a project, no estimate, never planned on a day, not from Outlook
update todo t set kind = 'action'
where t.kind = 'task'
  and (exists (select 1 from logbook_entry e, jsonb_array_elements(e.actions) s
               where s->>'id' = t.id::text and s->'what' ? 'added')
       or (t.created_at >= date '2026-10-20' and t.est_hours is null and not t.must_this_week
           and t.source is null and (t.project_id is not null or t.group_project_id is not null)
           and not exists (select 1 from todo_slot sl where sl.todo_id = t.id)));

create or replace function member_actions_for(p uuid) returns table (
  id uuid, title text, note text, links text[], group_project_id uuid, is_done boolean, done_at timestamptz,
  due_on date, created_at timestamptz
)
language sql stable security definer set search_path = public as $$
  select t.id, t.title, t.note, t.links, t.group_project_id, t.is_done, t.done_at, t.due_on, t.created_at
  from todo t
  where t.user_id = p and t.group_project_id is not null and not t.is_cancelled and t.kind = 'action'
    and (p = auth.uid() or is_supervisor())
  order by t.is_done, t.created_at
$$;
