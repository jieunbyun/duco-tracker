-- 0013_undo.sql — one undo for every tab. Each change the app makes is logged
-- with the row as it was and as it became, tagged with the action it belongs
-- to (the app sends an "x-undo-group" header with every write). undo_group()
-- plays an action's changes backwards: added rows are removed, edited rows
-- get their old values back, deleted rows (and anything deleted along with
-- them) come back with their original ids.
--
-- Writes without the header (the SQL editor, the calendar sync, undo itself)
-- are not logged. The log keeps two days.
create table change_log (
  id       bigserial primary key,
  user_id  uuid not null default auth.uid() references auth.users on delete cascade,
  grp      text not null,                                   -- one action in the app
  tbl      text not null,
  op       text not null check (op in ('INSERT', 'UPDATE', 'DELETE')),
  old_row  jsonb,
  new_row  jsonb,
  at       timestamptz not null default now()
);
create index on change_log (user_id, grp);
create index on change_log (user_id, at);

alter table change_log enable row level security;
create policy owner_all on change_log for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());

create function log_change() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  me uuid := auth.uid();
  g  text := nullif(current_setting('request.headers', true), '')::json ->> 'x-undo-group';
begin
  if me is null or g is null or current_setting('app.undoing', true) = 'on' then
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

-- every table the app writes to
do $$
declare t text;
begin
  foreach t in array array[
    'area', 'area_target', 'category', 'user_setting', 'project', 'milestone', 'time_entry', 'todo', 'todo_slot',
    'cv_entry', 'calendar_feed', 'calendar_ignore', 'reading', 'reading_note',
    'pw_node', 'pw_link', 'pw_revision', 'pw_asset'
  ] loop
    if to_regclass(t) is not null then
      execute format('create trigger undo_log after insert or update or delete on %I
                        for each row execute function log_change()', t);
    end if;
  end loop;
end $$;

-- Reverse one logged change. Columns computed by the database are left to it.
create function undo_change(c change_log) returns void
language plpgsql set search_path = public as $$
declare
  rel   regclass := c.tbl::regclass;
  cols  text;
  pk    text;
  rec   jsonb := coalesce(c.old_row, c.new_row);
begin
  select string_agg(quote_ident(attname), ', ' order by attnum) into cols
    from pg_attribute where attrelid = rel and attnum > 0 and not attisdropped and attgenerated = '';
  select string_agg(format('%I = ($1 ->> %L)::%s', a.attname, a.attname, format_type(a.atttypid, a.atttypmod)), ' and ')
    into pk
    from pg_index i join pg_attribute a on a.attrelid = i.indrelid and a.attnum = any(i.indkey)
    where i.indrelid = rel and i.indisprimary;

  if c.op = 'INSERT' then
    execute format('delete from %s where %s', rel, pk) using rec;
  elsif c.op = 'UPDATE' then
    execute format('update %s set (%s) = (select %s from jsonb_populate_record(null::%s, $1)) where %s',
                   rel, cols, cols, rel, pk) using rec;
  else
    execute format('insert into %s (%s) select %s from jsonb_populate_record(null::%s, $1) on conflict do nothing',
                   rel, cols, cols, rel) using rec;
  end if;
end $$;

-- Undo one action: its changes, newest first. A row can only come back once
-- what it points at is back, so anything that cannot go yet is retried after
-- the rest. Returns how many changes were reversed.
create function undo_group(g text) returns int
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
      exception when foreign_key_violation or unique_violation or check_violation then
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
