-- 0035_member_projects.sql — anyone in the group may start a shared project, and
-- everyone on a project (its collaborators) may add others from the group to it.
-- Taking someone off a project, and deleting one, stay yours.
--
-- A project is started through create_group_project, which adds its creator as
-- a collaborator in the same step: a plain insert would leave them unable to
-- see the project they had just made (they are not on it yet). Safe to re-run.

create or replace function create_group_project(
  p_title text, p_aim text, p_status text, p_start date, p_end date, p_folder text
) returns uuid
language plpgsql security definer set search_path = public as $$
declare v uuid;
begin
  if not is_group_member() then
    raise exception 'Only members of the group can start a project.';
  end if;
  insert into group_project (title, aim, status, start_on, end_on, folder_url)
  values (p_title, p_aim, coalesce(p_status, 'active'), p_start, p_end, p_folder)
  returning id into v;
  insert into group_project_member (project_id, user_id) values (v, auth.uid())
  on conflict do nothing;
  return v;
end
$$;
revoke all on function create_group_project(text, text, text, date, date, text) from public, anon;
grant execute on function create_group_project(text, text, text, date, date, text) to authenticated;

-- collaborators add others to a project they are on (removing stays yours)
drop policy if exists add_collaborator on group_project_member;
create policy add_collaborator on group_project_member for insert to authenticated
  with check (is_on_project(project_id));
