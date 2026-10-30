-- 0047_action_time.sql — the time a member gives their actions on shared projects:
-- the hours they project for one, and the hours they log on it (a date with start
-- and end times, or just hours). You read these, to see where their time goes, and
-- can flag an action as over- or underspent; nothing is worked out for you. Other
-- members never see them. Safe to re-run.
--
-- action_plan   the hours projected for an action
-- action_time   one sitting on an action
-- action_flag   your flag on an action; theirs to see, only yours to change

-- an action of your own on a shared project
create or replace function is_my_shared_action(a uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from todo t
    where t.id = a and t.user_id = auth.uid() and t.kind = 'action' and t.group_project_id is not null
  )
$$;
revoke all on function is_my_shared_action(uuid) from public, anon;
grant execute on function is_my_shared_action(uuid) to authenticated;

create table if not exists action_plan (
  action_id     uuid primary key references todo on delete cascade,
  user_id       uuid not null default auth.uid() references auth.users on delete cascade,
  planned_hours numeric not null check (planned_hours >= 0)
);
create table if not exists action_time (
  id          uuid primary key default gen_random_uuid(),
  action_id   uuid not null references todo on delete cascade,
  user_id     uuid not null default auth.uid() references auth.users on delete cascade,
  worked_on   date not null default current_date,
  start_time  time,
  end_time    time,
  hours       numeric not null check (hours > 0),
  created_at  timestamptz not null default now(),
  check (end_time is null or start_time is null or end_time > start_time)
);
create index if not exists action_time_action on action_time (action_id);
create index if not exists action_time_user on action_time (user_id, worked_on);
create table if not exists action_flag (
  action_id  uuid primary key references todo on delete cascade,
  flag       text not null check (flag in ('over', 'under')),
  flagged_at timestamptz not null default now()
);

alter table action_plan enable row level security;
alter table action_time enable row level security;
alter table action_flag enable row level security;

-- yours, on your own actions; you (the supervisor) read a member's, except on their
-- private milestones (can_see_action leaves those out)
drop policy if exists mine on action_plan;
create policy mine on action_plan for all to authenticated
  using (user_id = auth.uid()) with check (user_id = auth.uid() and is_my_shared_action(action_id));
drop policy if exists read_member on action_plan;
create policy read_member on action_plan for select to authenticated
  using (is_supervisor() and can_see_action(action_id));

drop policy if exists mine on action_time;
create policy mine on action_time for all to authenticated
  using (user_id = auth.uid()) with check (user_id = auth.uid() and is_my_shared_action(action_id));
drop policy if exists read_member on action_time;
create policy read_member on action_time for select to authenticated
  using (is_supervisor() and can_see_action(action_id));

drop policy if exists read on action_flag;
create policy read on action_flag for select to authenticated
  using (is_supervisor() or is_my_shared_action(action_id));
drop policy if exists write on action_flag;
create policy write on action_flag for all to authenticated
  using (is_supervisor()) with check (is_supervisor());

grant select, insert, update, delete on table action_plan, action_time, action_flag to authenticated;

-- A member's hours on their private milestones count in a project's total, but you
-- see only that: the project, the date and the hours, never what they were spent on.
create or replace function member_private_time(p uuid)
returns table (group_project_id uuid, worked_on date, hours numeric)
language sql stable security definer set search_path = public as $$
  select t.group_project_id, a.worked_on, sum(a.hours)
  from action_time a join todo t on t.id = a.action_id
  where is_supervisor() and t.user_id = p
    and t.group_milestone_id is not null and not sees_milestone(t.group_milestone_id)
  group by t.group_project_id, a.worked_on
$$;
revoke all on function member_private_time(uuid) from public, anon;
grant execute on function member_private_time(uuid) to authenticated;

do $$
declare t text;
begin
  if to_regprocedure('log_change()') is not null then
    foreach t in array array['action_plan', 'action_time', 'action_flag'] loop
      execute format('drop trigger if exists undo_log on %I', t);
      execute format('create trigger undo_log after insert or update or delete on %I for each row execute function log_change()', t);
    end loop;
  end if;
end $$;
