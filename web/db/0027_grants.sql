-- 0027_grants.sql — open the app's tables to the signed-in role explicitly.
-- From 30 October 2026, Supabase no longer grants API access to new tables in
-- "public" automatically: a table created after that date answers "permission
-- denied" until it is granted. This file grants every table the app uses to
-- signed-in users only (not anonymous visitors); row-level security still
-- decides which rows each person sees. Safe to run again at any time, and run
-- it after any SQL file that creates a table (later files carry their own grant).
do $$
declare t text;
begin
  foreach t in array array[
    'area', 'area_target', 'category', 'user_setting', 'project', 'milestone', 'time_entry', 'entry_hours',
    'todo', 'todo_slot', 'cv_entry', 'calendar_feed', 'calendar_ignore', 'reading', 'reading_note',
    'pw_node', 'pw_link', 'pw_revision', 'pw_contributor', 'pw_asset', 'asset_contributor', 'asset_publication', 'asset_link',
    'change_log', 'group_member', 'group_project', 'group_project_member', 'group_milestone',
    'logbook_entry', 'logbook_revision', 'logbook_comment', 'action_comment'
  ] loop
    if to_regclass(t) is not null then
      execute format('grant select, insert, update, delete on table %I to authenticated', t);
    end if;
  end loop;
end $$;

grant usage, select on all sequences in schema public to authenticated;
