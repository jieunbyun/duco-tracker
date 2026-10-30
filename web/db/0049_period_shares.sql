-- 0049_period_shares.sql — a member's shares over a period you choose: whole
-- percentages by project, as in 0048. Worked out from the hours here, since rounded
-- weekly shares don't add up; the hours stay in here. Safe to re-run.
create or replace function member_period_shares(p uuid, d0 date default null, d1 date default null)
returns table (group_project_id uuid, share integer)
language sql stable security definer set search_path = public as $$
  with spent as (
    select t.group_project_id as project, sum(a.hours) as total
    from action_time a join todo t on t.id = a.action_id
    where is_supervisor() and t.user_id = p and t.group_project_id is not null
      and (d0 is null or a.worked_on >= d0) and (d1 is null or a.worked_on <= d1)
    group by 1
  )
  select project, round(100 * total / sum(total) over ())::integer
  from spent
  order by 2 desc
$$;
revoke all on function member_period_shares(uuid, date, date) from public, anon;
grant execute on function member_period_shares(uuid, date, date) to authenticated;
