-- 0026_action_log.sql — the Logbook is built on actions: each action has its
-- own dated thread of comments and links. A member writes on their own actions;
-- you reply on theirs. The old "what I did / results / next" entries stay
-- readable but are no longer written.
--
-- action_comment  one comment (and/or links) on an action, by its author
create table action_comment (
  id          uuid primary key default gen_random_uuid(),
  action_id   uuid not null references todo on delete cascade,
  author_id   uuid not null default auth.uid() references auth.users on delete cascade,
  body        text,
  links       text[] not null default '{}',
  created_at  timestamptz not null default now(),
  check (coalesce(btrim(body), '') <> '' or cardinality(links) > 0)
);
create index on action_comment (action_id, created_at);

-- a shared project's milestone, for actions on shared projects
alter table todo add column if not exists group_milestone_id uuid references group_milestone on delete set null;

-- who may see an action's thread: its owner, and you for members' actions on shared projects
create function can_see_action(a uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from todo t
    where t.id = a and t.kind = 'action'
      and (t.user_id = auth.uid() or (t.group_project_id is not null and is_supervisor()))
  )
$$;

alter table action_comment enable row level security;
create policy read   on action_comment for select to authenticated using (can_see_action(action_id));
create policy add    on action_comment for insert to authenticated
  with check (author_id = auth.uid() and can_see_action(action_id));
-- a comment can be taken back on the day it was written; after that it stays
create policy remove on action_comment for delete to authenticated
  using (author_id = auth.uid() and created_at > now() - interval '1 day');

-- the notes already on actions become their first comments (a dated line keeps its date)
insert into action_comment (action_id, author_id, body, created_at)
select t.id, t.user_id,
       regexp_replace(line, '^\d{4}-\d{2}-\d{2}: ', ''),
       case when line ~ '^\d{4}-\d{2}-\d{2}: ' then substring(line from 1 for 10)::date::timestamptz else t.created_at end
from todo t, regexp_split_to_table(t.note, E'\n') as line
where t.kind = 'action' and t.note is not null and btrim(line) <> '';
update todo set note = null where kind = 'action' and note is not null;

-- how lively each shared project is: comments on its actions since a date
create function group_project_activity(since date) returns table (group_project_id uuid, comments bigint)
language sql stable security definer set search_path = public as $$
  select t.group_project_id, count(*)
  from action_comment c join todo t on t.id = c.action_id
  where t.group_project_id is not null and c.created_at >= since
    and (is_supervisor() or t.user_id = auth.uid())
  group by t.group_project_id
$$;

-- a member's actions, now with their milestone
drop function if exists member_actions_for(uuid);
create function member_actions_for(p uuid) returns table (
  id uuid, title text, links text[], group_project_id uuid, group_milestone_id uuid,
  is_done boolean, done_at timestamptz, created_at timestamptz, sort_order integer
)
language sql stable security definer set search_path = public as $$
  select t.id, t.title, t.links, t.group_project_id, t.group_milestone_id, t.is_done, t.done_at, t.created_at, t.sort_order
  from todo t
  where t.user_id = p and t.group_project_id is not null and not t.is_cancelled and t.kind = 'action'
    and (p = auth.uid() or is_supervisor())
  order by t.is_done, t.sort_order, t.created_at
$$;

do $$
begin
  if to_regprocedure('log_change()') is not null then
    create trigger undo_log after insert or update or delete on action_comment
      for each row execute function log_change();
  end if;
end $$;
