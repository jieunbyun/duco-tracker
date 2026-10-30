-- 0045_project_bin.sql — anyone on a shared project can delete it, into your bin:
-- it goes for everyone on it, and you restore it or delete it for good. A real
-- delete would take what they cannot see with it (your private milestones and
-- others', and your Planning copies of them), so that stays yours. Safe to re-run.
alter table group_project add column if not exists deleted_at timestamptz;
alter table group_project add column if not exists deleted_by uuid references auth.users on delete set null;

-- nobody is "on" a binned project: its milestones, actions and logbook rules all
-- go through this, so it goes for members everywhere at once, and nothing is lost
create or replace function is_on_project(p uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from group_project_member m
    join group_member g on g.user_id = m.user_id
    join group_project x on x.id = m.project_id
    where m.project_id = p and m.user_id = auth.uid() and g.active and x.deleted_at is null
  )
$$;

-- a function, because the project is out of the caller's sight as soon as it is done
create or replace function bin_group_project(p uuid) returns void
language plpgsql security definer set search_path = public as $$
begin
  if not is_on_project(p) then
    raise exception 'Only someone on the project can delete it.';
  end if;
  update group_project set deleted_at = now(), deleted_by = auth.uid() where id = p;
end
$$;
revoke all on function bin_group_project(uuid) from public, anon;
grant execute on function bin_group_project(uuid) to authenticated;
