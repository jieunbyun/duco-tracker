-- 0100_todo_slot.sql
--
-- The Week tab's to-do board: a to-do is planned onto one or more DAYS, never
-- onto a clock time. Each planned day is a "sitting".
--
--   * planned_hours is OPTIONAL. Null means "this day, however long it takes".
--   * a to-do with no sittings is unplanned, and appears in the list under the
--     board. Every to-do that exists today is in that state, so there is
--     nothing to backfill.
--   * session_id is filled in when the sitting is logged. It points at the
--     work_session that logging produced, which is what puts the block on the
--     week calendar and marks it "from to-do".
--
-- There is deliberately NO unique constraint on (todo_id, planned_on): a task
-- may have two sittings on the same day, a morning one and an afternoon one.
--
-- Apply this in the Supabase SQL editor BEFORE deploying the app code that
-- uses it, or the app will request columns the database does not have.

create table if not exists todo_slot (
  id            uuid primary key default gen_random_uuid(),
  todo_id       uuid not null references todo(id) on delete cascade,
  user_id       uuid not null references app_user(id) on delete cascade,
  planned_on    date not null,
  planned_hours numeric,
  session_id    uuid references work_session(id) on delete set null,
  sort_order    int,
  created_at    timestamptz not null default now()
);

create index if not exists todo_slot_day_idx
  on todo_slot (user_id, planned_on);
create index if not exists todo_slot_todo_idx
  on todo_slot (todo_id);

-- A sitting says what someone is working on and when, so it is as private as
-- the to-do it belongs to: owner-only, both directions.
alter table todo_slot enable row level security;

drop policy if exists todo_slot_own on todo_slot;
create policy todo_slot_own on todo_slot
  for all
  using      (user_id = (select id from app_user
                         where auth_user_id = auth.uid()))
  with check (user_id = (select id from app_user
                         where auth_user_id = auth.uid()));

-- NOTE: if your existing `todo` table's policy expresses ownership
-- differently, copy that expression here instead — the two must agree, or a
-- to-do will be visible while its sittings are not (the board would silently
-- read back empty).
