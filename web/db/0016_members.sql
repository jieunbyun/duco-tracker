-- 0016_members.sql — students become members (they contribute to publications,
-- awards, teaching, outreach and grants, not only to supervised projects).
-- A member is picked from your Planning projects under Research › Supervision,
-- which already name them, so the name is not typed twice; anyone else (a
-- collaborator) can still be added by name. And a shared project has a lead —
-- you, for the projects you lead.
alter table group_member drop constraint if exists group_member_role_check;
update group_member set role = 'member' where role in ('student', 'collaborator');
alter table group_member add constraint group_member_role_check check (role in ('supervisor', 'member'));
alter table group_member add column if not exists planning_project_id uuid references project on delete set null;

alter table group_project add column if not exists lead_id uuid references group_member on delete set null;

drop function if exists add_group_member(text, text, text);
create function add_group_member(p_email text, p_name text, p_planning_project uuid default null) returns uuid
language plpgsql security definer set search_path = public as $$
declare uid uuid;
begin
  if not is_supervisor() then
    raise exception 'Only the supervisor can add members.';
  end if;
  if p_planning_project is not null
     and not exists (select 1 from project where id = p_planning_project and user_id = auth.uid()) then
    raise exception 'That Planning project is not yours.';
  end if;
  select id into uid from auth.users where lower(email) = lower(trim(p_email));
  if uid is null then
    raise exception 'No account for % yet. Invite them first in Supabase (Authentication › Users › Invite user).', trim(p_email);
  end if;
  insert into group_member (user_id, role, display_name, email, planning_project_id)
  values (uid, 'member', trim(p_name), lower(trim(p_email)), p_planning_project)
  on conflict (user_id) do update
    set display_name = excluded.display_name, role = 'member', active = true,
        planning_project_id = excluded.planning_project_id;
  return uid;
end $$;
