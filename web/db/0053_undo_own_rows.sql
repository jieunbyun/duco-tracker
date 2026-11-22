-- 0053_undo_own_rows.sql — the undo log keeps only rows that are yours to see.
--
-- An action can change rows that belong to someone else along the way: when a
-- member deletes a shared project's milestone, your Planning milestone that stands
-- for it is unlinked, your hours on it and your actions' links to it go. Until now
-- each of those rows was copied, whole, into the undo log of whoever made the change
-- — and they can read their own log. A member could read your private milestone
-- notes and hours that way. Now a row that belongs to someone else (and is not one
-- the group shares) stays out of the log, and what was logged so far is cleared.
--
-- Undo could never put such rows back anyway: it runs as you, and they are not
-- yours to write. Undoing that member's delete now brings the milestone back,
-- without your rows (it used to stop with an error instead; see undo_group below).
-- Safe to re-run.

-- Whose a row is, for the log: null for a row the group shares (anyone who can change
-- it can see it), else the person it belongs to.
create or replace function change_owner(tbl text, r jsonb) returns text
language sql immutable set search_path = public as $$
  select case
    -- these name someone, but are not theirs: the group's, seen by those on it
    when tbl in ('group_member', 'group_project_member', 'asset_contributor') then null
    -- outputs are kept by everyone on them, and read by the whole group
    when tbl = 'pw_asset' then null
    -- the person the item is about is user_id; the item is owner_id's
    when tbl = 'pw_contributor' then r ->> 'owner_id'
    -- a shared milestone: public ones are everyone's on the project; private ones, their maker's
    when tbl = 'group_milestone' then case when coalesce((r ->> 'is_private')::boolean, false) then r ->> 'owner_id' end
    else coalesce(r ->> 'user_id', r ->> 'author_id')
  end
$$;

create or replace function log_change() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  me    uuid := auth.uid();
  g     text := nullif(current_setting('request.headers', true), '')::json ->> 'x-undo-group';
  owner text;
begin
  if me is null or g is null or current_setting('app.undoing', true) = 'on' then
    return null;
  end if;
  -- someone else's row, changed along the way: not for your log
  owner := change_owner(tg_table_name, to_jsonb(case when tg_op = 'DELETE' then old else new end));
  if owner is not null and owner <> me::text then
    return null;
  end if;
  insert into change_log (user_id, grp, tbl, op, old_row, new_row)
  values (me, g, tg_table_name, tg_op,
          case when tg_op <> 'INSERT' then to_jsonb(old) end,
          case when tg_op <> 'DELETE' then to_jsonb(new) end);
  if random() < 0.02 then
    delete from change_log where user_id = me and at < now() - interval '2 days';
  end if;
  return null;
end $$;

-- Undo puts rows back newest first, retrying any that cannot go yet. A row whose
-- access rule looks at another row (your hours on a shared milestone need the
-- milestone) is refused until that row is back: retried too, like a missing link,
-- instead of stopping the whole undo. (Undoing a shared milestone's delete stopped
-- here before, with "violates row-level security policy".)
create or replace function undo_group(g text) returns int
language plpgsql set search_path = public as $$
declare
  me       uuid := auth.uid();
  pending  bigint[];
  failed   bigint[];
  c        change_log;
  n        int := 0;
begin
  perform set_config('app.undoing', 'on', true);
  select array_agg(id order by id desc) into pending from change_log where user_id = me and grp = g;
  if pending is null then
    return 0;
  end if;
  loop
    failed := '{}';
    for c in select * from change_log where id = any(pending) order by id desc loop
      begin
        perform undo_change(c);
        n := n + 1;
      exception when foreign_key_violation or unique_violation or check_violation or insufficient_privilege then
        failed := failed || c.id;
      end;
    end loop;
    exit when cardinality(failed) = 0;
    if cardinality(failed) = cardinality(pending) then
      raise exception 'Could not undo: later changes depend on it.';
    end if;
    pending := failed;
  end loop;
  delete from change_log where user_id = me and grp = g;
  return n;
end $$;

-- A shared milestone put back by undo: the Planning milestones that stood for it were
-- unlinked when it was deleted (each person's own, outside the undo log). Link them
-- again — in a Planning project standing for its project, the unlinked one with its
-- title — so the next change to it does not bring in a second copy. Otherwise as 0041.
create or replace function group_milestone_to_planning() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if coalesce(current_setting('app.pushing', true), '') = 'on' then return null; end if;
  if tg_op = 'INSERT' and coalesce(current_setting('app.undoing', true), '') = 'on' then
    -- (a private one's own Planning milestone comes back with it, from the log)
    if not new.is_private then
      update milestone m set group_milestone_id = new.id
      from project p
      where p.group_project_id = new.project_id and m.project_id = p.id
        and m.id = (select x.id from milestone x
                    where x.project_id = p.id and x.group_milestone_id is null and x.title = new.title
                    order by x.created_at limit 1)
        and not exists (select 1 from milestone y where y.user_id = p.user_id and y.group_milestone_id = new.id);
    end if;
    return null;
  end if;
  perform sync_shared_milestones(p.id) from project p where p.group_project_id = new.project_id;
  return null;
end $$;

-- what is already in anyone's log that was not theirs to see
delete from change_log
where change_owner(tbl, coalesce(new_row, old_row)) is not null
  and change_owner(tbl, coalesce(new_row, old_row)) <> user_id::text;
