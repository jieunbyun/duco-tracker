-- 0101_todo_placement.sql
--
-- Place a to-do the same way every other piece of work in the app is placed:
-- category -> project -> milestone. Until now a to-do carried only a
-- project_id, chosen from a flat list of every project, so the work it
-- belonged to had to be re-chosen from scratch when the sitting was logged.
--
--   * category_id lets a to-do be categorised with no project at all
--     ("Mark lab reports" is Teaching, and belongs to no project).
--   * milestone_id lets it accrue against the milestone it advances.
--
-- Both are OPTIONAL and default to null, so every to-do that exists today is
-- unchanged and still valid — nothing to backfill. They are used to pre-fill
-- the log panel when a sitting is ticked off, so a to-do that was placed when
-- it was written needs no choosing at all when it is logged.
--
-- Deleting a category or milestone must not delete someone's to-do, so both
-- are ON DELETE SET NULL: the to-do survives, simply unplaced.
--
-- Apply this in the Supabase SQL editor BEFORE deploying the app code that
-- uses it, or the app will request columns the database does not have.

alter table todo
  add column if not exists category_id uuid
    references category(id) on delete set null;

alter table todo
  add column if not exists milestone_id uuid
    references project_milestone(id) on delete set null;

create index if not exists todo_category_idx on todo (category_id);
create index if not exists todo_milestone_idx on todo (milestone_id);

-- No RLS change is needed: these are columns on `todo`, which is already
-- owner-only, and they are read and written through the same policy.
--
-- Existing to-dos that already name a project can be given that project's
-- category in one pass, if you would like them to arrive pre-placed too.
-- Optional, and safe to skip:
--
--   update todo t
--      set category_id = p.category_id
--     from project p
--    where t.project_id = p.id
--      and t.category_id is null
--      and p.category_id is not null;
