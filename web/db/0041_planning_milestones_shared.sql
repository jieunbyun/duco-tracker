-- 0041_planning_milestones_shared.sql — a Planning project that stands for a
-- shared project keeps all of that project's milestones in one place, both
-- ways. A milestone you add in Planning goes to the shared project as a
-- private one (only you see it); linking a project sends its milestones over
-- the same way. Editing a shared milestone in Planning (title, dates, hard
-- deadline, order, what it comes after) edits it on the shared project — for
-- a public one, for everyone on the project. Deleting one of your private ones
-- in either place deletes it in both (logged time stays on the project). A
-- milestone still comes after milestones of its own kind only. Needs 0040.
-- Safe to re-run.

-- Send one Planning milestone of a linked project to the shared project, as a
-- private one of yours, with your hours.
create or replace function push_to_shared(mid uuid) returns void
language plpgsql security definer set search_path = public as $$
declare
  m        milestone;
  pr       project;
  gid      uuid := gen_random_uuid();
  undoing  text := coalesce(current_setting('app.undoing', true), '');
  pushing  text := coalesce(current_setting('app.pushing', true), '');
begin
  select * into m from milestone where id = mid;
  if m.id is null or m.group_milestone_id is not null then return; end if;
  select * into pr from project where id = m.project_id;
  if pr.group_project_id is null then return; end if;
  perform set_config('app.undoing', 'on', true);
  perform set_config('app.pushing', 'on', true); -- the shared side is not synced back while this runs
  insert into group_milestone (id, project_id, title, start_on, due_on, hard_deadline, sort_order, done, done_on, is_private, after_ids)
  values (gid, pr.group_project_id, m.title,
          m.start_on, m.due_on, m.hard_deadline, m.sort_order, m.status = 'done',
          case when m.status = 'done' then current_date end, true,
          -- what it comes after, among your private ones there
          coalesce(array(select a.group_milestone_id from milestone a join group_milestone g on g.id = a.group_milestone_id
                         where a.id = any(m.after_ids) and g.is_private and g.owner_id = m.user_id), '{}'));
  update milestone set group_milestone_id = gid where id = m.id;
  if m.planned_hours is not null then
    insert into group_milestone_hours (milestone_id, user_id, planned_hours) values (gid, m.user_id, m.planned_hours)
    on conflict (milestone_id, user_id) do update set planned_hours = excluded.planned_hours;
  end if;
  perform set_config('app.pushing', pushing, true);
  perform set_config('app.undoing', undoing, true);
end $$;
revoke all on function push_to_shared(uuid) from public, anon;
grant execute on function push_to_shared(uuid) to authenticated;

-- the shared side follows into Planning, except while Planning is pushing to it,
-- and except for a milestone brought back by undo (its Planning one comes back with it)
create or replace function group_milestone_to_planning() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if coalesce(current_setting('app.pushing', true), '') = 'on' then return null; end if;
  if tg_op = 'INSERT' and coalesce(current_setting('app.undoing', true), '') = 'on' then return null; end if;
  perform sync_shared_milestones(p.id) from project p where p.group_project_id = new.project_id;
  return null;
end $$;

-- linking: the shared milestones come in, then yours go over (and what they come after, once all are there)
create or replace function project_shared_link() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  r   record;
  was text := coalesce(current_setting('app.undoing', true), '');
begin
  perform sync_shared_milestones(new.id);
  if new.group_project_id is not null then
    for r in select id from milestone where project_id = new.id and group_milestone_id is null order by sort_order loop
      perform push_to_shared(r.id);
    end loop;
    perform set_config('app.undoing', 'on', true);
    update group_milestone g set after_ids = coalesce(array(
        select a.group_milestone_id from milestone a join group_milestone ga on ga.id = a.group_milestone_id
        where a.id = any(m.after_ids) and ga.is_private and ga.owner_id = m.user_id), '{}')
    from milestone m
    where m.project_id = new.id and m.group_milestone_id = g.id and g.is_private and g.owner_id = m.user_id;
    perform set_config('app.undoing', was, true);
  end if;
  return null;
end $$;

-- a milestone added in Planning to a linked project goes over
create or replace function planning_milestone_added() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  perform push_to_shared(new.id);
  return null;
end $$;
drop trigger if exists planning_milestone_added on milestone;
create trigger planning_milestone_added after insert on milestone
  for each row when (new.group_milestone_id is null) execute function planning_milestone_added();

-- edits in Planning reach the shared milestone
create or replace function planning_to_shared() returns trigger
language plpgsql security definer set search_path = public as $$
declare was text := coalesce(current_setting('app.undoing', true), '');
begin
  -- only your own edits go over: not the changes that come back from the shared side
  if new.group_milestone_id is null or pg_trigger_depth() > 1 then return null; end if;
  perform set_config('app.undoing', 'on', true);
  if new.planned_hours is distinct from old.planned_hours then
    if new.planned_hours is null then
      delete from group_milestone_hours where milestone_id = new.group_milestone_id and user_id = new.user_id;
    else
      insert into group_milestone_hours (milestone_id, user_id, planned_hours)
      values (new.group_milestone_id, new.user_id, new.planned_hours)
      on conflict (milestone_id, user_id) do update set planned_hours = excluded.planned_hours
        where group_milestone_hours.planned_hours is distinct from excluded.planned_hours;
    end if;
  end if;
  -- ticked done (or reopened) in Planning: so is the shared milestone
  if (new.status = 'done') is distinct from (old.status = 'done') then
    update group_milestone set done = (new.status = 'done'), done_on = case when new.status = 'done' then current_date end
    where id = new.group_milestone_id and done is distinct from (new.status = 'done');
  end if;
  -- what it is, when and after what: the shared milestone takes it
  if (new.title, new.start_on, new.due_on, new.hard_deadline, new.sort_order, new.after_ids)
     is distinct from (old.title, old.start_on, old.due_on, old.hard_deadline, old.sort_order, old.after_ids) then
    update group_milestone g set
      title = new.title, start_on = new.start_on, due_on = new.due_on, hard_deadline = new.hard_deadline,
      sort_order = new.sort_order,
      after_ids = coalesce(array(select a.group_milestone_id from milestone a
                                 where a.id = any(new.after_ids) and a.group_milestone_id is not null), '{}')
    where g.id = new.group_milestone_id;
  end if;
  perform set_config('app.undoing', was, true);
  return null;
end $$;
drop trigger if exists planning_to_shared on milestone;
create trigger planning_to_shared after update of planned_hours, status, title, start_on, due_on, hard_deadline, sort_order, after_ids
  on milestone for each row execute function planning_to_shared();

-- deleting one of your private ones, in either place, deletes it in both
create or replace function planning_milestone_gone() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  -- (not when the shared one is what is being deleted)
  if old.group_milestone_id is not null and pg_trigger_depth() = 1 then
    delete from group_milestone where id = old.group_milestone_id and is_private and owner_id = old.user_id;
  end if;
  return null;
end $$;
drop trigger if exists planning_milestone_gone on milestone;
create trigger planning_milestone_gone after delete on milestone
  for each row execute function planning_milestone_gone();

create or replace function shared_milestone_gone() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if old.is_private then
    delete from milestone where group_milestone_id = old.id and user_id = old.owner_id;
  end if;
  return old;
end $$;
drop trigger if exists shared_milestone_gone on group_milestone;
create trigger shared_milestone_gone before delete on group_milestone
  for each row execute function shared_milestone_gone();
