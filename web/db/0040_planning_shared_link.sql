-- 0040_planning_shared_link.sql — one of your Planning projects can stand for a
-- shared project. Its milestones then come into the Planning project as
-- ordinary milestones (marked as shared): the public ones, and your own
-- private ones. Their title, dates, order, what they come after, hard deadline
-- and done follow the shared project; your notes stay yours. Their planned
-- hours are "your hours" on the shared milestone, the same figure in both
-- places. Ticking one done in Planning ticks the shared milestone. A shared
-- milestone that is deleted, or a link that is undone, leaves the Planning
-- milestone as an ordinary one of yours, with its logged time. Nothing here is
-- seen by anyone else. Needs 0037 and 0038. Safe to re-run.
alter table project   add column if not exists group_project_id   uuid references group_project   on delete set null;
alter table milestone add column if not exists group_milestone_id uuid references group_milestone on delete set null;
create unique index if not exists project_group_link_idx   on project   (user_id, group_project_id)   where group_project_id is not null;
create unique index if not exists milestone_group_link_idx on milestone (user_id, group_milestone_id) where group_milestone_id is not null;

-- a Planning project can only stand for a shared project you can see
drop policy if exists shared_project_ok on project;
create policy shared_project_ok on project as restrictive for all to authenticated
  using (true)
  with check (group_project_id is null or is_supervisor() or is_on_project(group_project_id));

-- whether someone (not necessarily the caller) can see a shared milestone
create or replace function milestone_visible_to(g group_milestone, u uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select (not g.is_private or g.owner_id = u)
     and (exists (select 1 from group_member where user_id = u and role = 'supervisor' and active)
          or exists (select 1 from group_project_member m join group_member gm on gm.user_id = m.user_id
                     where m.project_id = g.project_id and m.user_id = u and gm.active))
$$;

-- Bring a Planning project's shared milestones in step. Changes made here are
-- kept out of the undo log (they follow from the change that was undone).
create or replace function sync_shared_milestones(p uuid) returns void
language plpgsql security definer set search_path = public as $$
declare
  pr  project;
  was text := coalesce(current_setting('app.undoing', true), '');
begin
  select * into pr from project where id = p;
  if pr.id is null then return; end if;
  perform set_config('app.undoing', 'on', true);

  -- milestones of a shared project it no longer stands for become ordinary ones
  update milestone m set group_milestone_id = null
  from group_milestone g
  where m.project_id = pr.id and m.group_milestone_id = g.id and g.project_id is distinct from pr.group_project_id;

  if pr.group_project_id is not null then
    -- new shared milestones come in, with your hours if you set some
    insert into milestone (user_id, project_id, title, status, start_on, due_on, planned_hours, hard_deadline, sort_order, group_milestone_id)
    select pr.user_id, pr.id, g.title, case when g.done then 'done' else 'active' end,
           case when g.due_on < g.start_on then null else g.start_on end, g.due_on,
           (select h.planned_hours from group_milestone_hours h where h.milestone_id = g.id and h.user_id = pr.user_id),
           g.hard_deadline, least(greatest(g.sort_order, -32768), 32767)::smallint, g.id
    from group_milestone g
    where g.project_id = pr.group_project_id and milestone_visible_to(g, pr.user_id)
      and not exists (select 1 from milestone m where m.user_id = pr.user_id and m.group_milestone_id = g.id);

    -- and all follow the shared project (what they come after, among this project's)
    update milestone m set
      title         = g.title,
      start_on      = case when g.due_on < g.start_on then null else g.start_on end,
      due_on        = g.due_on,
      hard_deadline = g.hard_deadline,
      sort_order    = least(greatest(g.sort_order, -32768), 32767)::smallint,
      status        = case when g.done then 'done' when m.status = 'done' then 'active' else m.status end,
      after_ids     = coalesce(array(select a.id from milestone a
                                     where a.project_id = pr.id and a.group_milestone_id = any(g.after_ids)), '{}')
    from group_milestone g
    where m.project_id = pr.id and m.group_milestone_id = g.id;
  end if;

  perform set_config('app.undoing', was, true);
end $$;
revoke all on function sync_shared_milestones(uuid) from public, anon;
grant execute on function sync_shared_milestones(uuid) to authenticated;

-- linking (or unlinking) a Planning project
create or replace function project_shared_link() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  perform sync_shared_milestones(new.id);
  return null;
end $$;
drop trigger if exists project_shared_link on project;
create trigger project_shared_link after insert or update of group_project_id on project
  for each row execute function project_shared_link();

-- a shared milestone made or changed: every Planning project standing for its project follows
create or replace function group_milestone_to_planning() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  perform sync_shared_milestones(p.id) from project p where p.group_project_id = new.project_id;
  return null;
end $$;
drop trigger if exists group_milestone_to_planning on group_milestone;
create trigger group_milestone_to_planning after insert or update on group_milestone
  for each row execute function group_milestone_to_planning();

-- your hours on a shared milestone are its Planning milestone's planned hours, and back
create or replace function shared_hours_to_planning() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  was text := coalesce(current_setting('app.undoing', true), '');
  ms  uuid;
  who uuid;
  h   numeric;
begin
  if tg_op = 'DELETE' then
    ms := old.milestone_id; who := old.user_id; h := null;
  else
    ms := new.milestone_id; who := new.user_id; h := new.planned_hours;
  end if;
  perform set_config('app.undoing', 'on', true);
  update milestone set planned_hours = h
  where user_id = who and group_milestone_id = ms and planned_hours is distinct from h;
  perform set_config('app.undoing', was, true);
  return null;
end $$;
drop trigger if exists shared_hours_to_planning on group_milestone_hours;
create trigger shared_hours_to_planning after insert or update or delete on group_milestone_hours
  for each row execute function shared_hours_to_planning();

create or replace function planning_to_shared() returns trigger
language plpgsql security definer set search_path = public as $$
declare was text := coalesce(current_setting('app.undoing', true), '');
begin
  if new.group_milestone_id is null then return null; end if;
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
  perform set_config('app.undoing', was, true);
  return null;
end $$;
drop trigger if exists planning_to_shared on milestone;
create trigger planning_to_shared after update of planned_hours, status on milestone
  for each row execute function planning_to_shared();
