-- 0101_todo_slot_cancel.sql
--
-- Cancelling ONE sitting — one planned day of a to-do — without touching the
-- to-do itself.
--
-- A plan made on Monday is a guess. When one of a task's days turns out not to
-- be needed, deleting the sitting loses the fact that it was ever planned, and
-- cancelling the whole to-do throws away the days that are still real. So a
-- sitting gets the same treatment a to-do already has: cancelled work is kept
-- for the record, struck through on the board, counted towards no day's
-- planned hours, and restorable.
--
--   * is_cancelled defaults to false, so every sitting that exists today stays
--     exactly as it is — nothing to backfill.
--   * only an UNLOGGED sitting can be cancelled (see db.set_slot_cancelled):
--     once a sitting has produced a work_session its hours are real, and it
--     must be re-opened before it can be dropped.
--
-- Apply this in the Supabase SQL editor BEFORE deploying the app code that
-- uses it, or the app will request a column the database does not have.

alter table todo_slot
  add column if not exists is_cancelled boolean not null default false;

-- The board reads a week of sittings per user and then splits live from
-- cancelled in Python, so the existing (user_id, planned_on) index still
-- serves every query; no new index is needed.
