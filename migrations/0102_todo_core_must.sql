-- 0102_todo_core_must.sql
--
-- One marker instead of two, and a second axis for the week's to-dos.
--
-- "High importance" (⭐) is gone. Core (🎯) is the only marker kept: it was
-- already the flag a logged session carries, and a to-do now carries it too,
-- so the board can split each day's planned hours into non-core and core
-- before anything is logged, and the log panel can start a core to-do's
-- session ticked as core.
--
--   * todo.is_core is backfilled from todo.is_important, so a to-do that was
--     starred keeps its mark, now as core.
--   * todo.must_this_week splits the week's list into "must be done this
--     week" and "flexible". It defaults to false: every existing to-do starts
--     out flexible.
--   * todo.is_important and project.high_importance are left in place and
--     simply no longer read or written, so nothing is lost and an older copy
--     of the app keeps working until it is redeployed. Drop them once the new
--     code is live, if you want them gone.
--
-- Apply this in the Supabase SQL editor BEFORE deploying the app code that
-- uses it, or the app will request columns the database does not have.

alter table todo
  add column if not exists is_core boolean not null default false;

alter table todo
  add column if not exists must_this_week boolean not null default false;

update todo set is_core = true where is_important and not is_core;
