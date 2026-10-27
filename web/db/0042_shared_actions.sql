-- 0042_shared_actions.sql — on a public milestone of a shared project, every
-- action is seen by everyone on the project (and you), with its thread, and
-- anyone there may comment on it. Each person still changes, ticks off and
-- deletes only the actions they logged. Actions on a private milestone, or on
-- a project with no milestone, stay their author's (and, for a member's on a
-- shared project, yours). Needs 0037. Safe to re-run.
create or replace function shared_action_visible(m uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from group_milestone g
    where g.id = m and not g.is_private and (is_supervisor() or is_on_project(g.project_id))
  )
$$;
revoke all on function shared_action_visible(uuid) from public, anon;
grant execute on function shared_action_visible(uuid) to authenticated;

-- reading only: changing a to-do stays its owner's (owner_all)
drop policy if exists read_shared on todo;
create policy read_shared on todo for select to authenticated
  using (kind = 'action' and group_milestone_id is not null and shared_action_visible(group_milestone_id));

-- who may see (and so comment on) an action's thread
create or replace function can_see_action(a uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from todo t
    where t.id = a and t.kind = 'action'
      and (t.user_id = auth.uid()
           or (t.group_milestone_id is not null and shared_action_visible(t.group_milestone_id))
           or (t.group_project_id is not null and is_supervisor()
               and (t.group_milestone_id is null or sees_milestone(t.group_milestone_id))))
  )
$$;

-- how lively each shared project is: the comments you can see
create or replace function group_project_activity(since date) returns table (group_project_id uuid, comments bigint)
language sql stable security definer set search_path = public as $$
  select t.group_project_id, count(*)
  from action_comment c join todo t on t.id = c.action_id
  where t.group_project_id is not null and c.created_at >= since
    and (t.user_id = auth.uid()
         or (t.group_milestone_id is not null and shared_action_visible(t.group_milestone_id))
         or (is_supervisor() and (t.group_milestone_id is null or sees_milestone(t.group_milestone_id))))
  group by t.group_project_id
$$;
