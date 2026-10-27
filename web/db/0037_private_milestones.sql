-- 0037_private_milestones.sql — a shared project's milestone is either public
-- (everyone on the project, and you) or private (only the person who made it;
-- a student's private milestone is hidden from you too). Anyone on the project
-- may make either kind. The kind is set when it is made and stays. A milestone
-- comes after milestones of its own kind only: public after public, private
-- after the same person's private ones. What hangs on a private milestone (an
-- action and its comments, a logbook entry) is seen by that person only.
-- Existing milestones are public. Safe to re-run.
alter table group_milestone add column if not exists is_private boolean not null default false;
alter table group_milestone add column if not exists owner_id uuid references auth.users on delete cascade;

-- whether the caller may see a milestone (looks past row-level security)
create or replace function sees_milestone(m uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from group_milestone g
    where g.id = m and (is_supervisor() or is_on_project(g.project_id))
      and (not g.is_private or g.owner_id = auth.uid())
  )
$$;
revoke all on function sees_milestone(uuid) from public, anon;
grant execute on function sees_milestone(uuid) to authenticated;

drop policy if exists all_of on group_milestone;
create policy all_of on group_milestone for all to authenticated
  using ((is_supervisor() or is_on_project(project_id)) and (not is_private or owner_id = auth.uid()))
  with check ((is_supervisor() or is_on_project(project_id)) and (not is_private or owner_id = auth.uid()));

-- who made it, and its kind, are fixed; it comes after milestones of its own kind only
create or replace function group_milestone_kind() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if tg_op = 'INSERT' then
    new.owner_id := auth.uid();
  else
    new.owner_id := old.owner_id;
    new.is_private := old.is_private;
  end if;
  -- milestones since deleted drop out of the list
  new.after_ids := array(select a from unnest(new.after_ids) a where exists (select 1 from group_milestone g where g.id = a));
  if exists (
    select 1 from unnest(new.after_ids) a join group_milestone g on g.id = a
    where g.project_id <> new.project_id or g.is_private <> new.is_private
       or (g.is_private and g.owner_id is distinct from new.owner_id)
  ) then
    raise exception 'A % milestone can only come after % ones.',
      case when new.is_private then 'private' else 'public' end,
      case when new.is_private then 'your own private' else 'public' end;
  end if;
  return new;
end $$;
drop trigger if exists group_milestone_kind on group_milestone;
create trigger group_milestone_kind before insert or update on group_milestone
  for each row execute function group_milestone_kind();

-- an action can only hang on a milestone its owner can see
drop policy if exists milestone_ok on todo;
create policy milestone_ok on todo as restrictive for all to authenticated
  using (true)
  with check (group_milestone_id is null or sees_milestone(group_milestone_id));

-- you read members' logbook entries, except those on their private milestones
drop policy if exists read on logbook_entry;
create policy read on logbook_entry for select to authenticated
  using (author_id = auth.uid()
         or (is_supervisor() and (group_milestone_id is null or sees_milestone(group_milestone_id))));

-- and their actions (with their comments), except those on their private milestones
create or replace function can_see_action(a uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from todo t
    where t.id = a and t.kind = 'action'
      and (t.user_id = auth.uid()
           or (t.group_project_id is not null and is_supervisor()
               and (t.group_milestone_id is null or sees_milestone(t.group_milestone_id))))
  )
$$;

create or replace function member_actions_for(p uuid) returns table (
  id uuid, title text, links text[], group_project_id uuid, group_milestone_id uuid,
  is_done boolean, done_at timestamptz, created_at timestamptz, sort_order integer
)
language sql stable security definer set search_path = public as $$
  select t.id, t.title, t.links, t.group_project_id, t.group_milestone_id, t.is_done, t.done_at, t.created_at, t.sort_order
  from todo t
  where t.user_id = p and t.group_project_id is not null and not t.is_cancelled and t.kind = 'action'
    and (p = auth.uid() or (is_supervisor() and (t.group_milestone_id is null or sees_milestone(t.group_milestone_id))))
  order by t.is_done, t.sort_order, t.created_at
$$;

create or replace function group_project_activity(since date) returns table (group_project_id uuid, comments bigint)
language sql stable security definer set search_path = public as $$
  select t.group_project_id, count(*)
  from action_comment c join todo t on t.id = c.action_id
  where t.group_project_id is not null and c.created_at >= since
    and (t.user_id = auth.uid()
         or (is_supervisor() and (t.group_milestone_id is null or sees_milestone(t.group_milestone_id))))
  group by t.group_project_id
$$;
