-- 0007_tentative.sql — tentative plans.
--
-- todo.is_tentative      on the calendar, but not counted as planned until
--                        confirmed (set by you, or by Outlook's own status)
-- todo.source_tentative  Outlook's tentative status as last seen, so a sync
--                        can tell when you accepted or declined there
alter table todo
  add column if not exists is_tentative     boolean not null default false,
  add column if not exists source_tentative boolean not null default false;
