-- 0048_time_shares_only.sql — a supervisor sees only the share of a member's time
-- that went to each project, week by week: never their hours, the times they
-- worked, or what they projected. Those stay the member's alone, so the rules
-- below replace the supervisor's reading of them (0047), and the flags on actions
-- go, since they would need those hours. Safe to re-run.
drop policy if exists read_member on action_plan;
drop policy if exists read_member on action_time;
drop function if exists member_private_time(uuid);
drop table if exists action_flag;

-- whole percentages of each week's logged time, by project (private milestones
-- count in their project, with nothing to tell them apart); the hours stay in here
create or replace function member_time_shares(p uuid)
returns table (week date, group_project_id uuid, share integer)
language sql stable security definer set search_path = public as $$
  with spent as (
    select date_trunc('week', a.worked_on::timestamp)::date as wk, t.group_project_id as project, sum(a.hours) as total
    from action_time a join todo t on t.id = a.action_id
    where is_supervisor() and t.user_id = p and t.group_project_id is not null
    group by 1, 2
  )
  select wk, project, round(100 * total / sum(total) over (partition by wk))::integer
  from spent
  order by wk desc, 3 desc
$$;
revoke all on function member_time_shares(uuid) from public, anon;
grant execute on function member_time_shares(uuid) to authenticated;
