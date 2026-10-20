-- 0020_core_target.sql — a weekly target for core hours (hours flagged core),
-- counted over every day of the week. Your figure is set in the app
-- (Planning › Edit targets and settings) or in etc/targets.private.sql; it is
-- never written here, as this file is public.
alter table user_setting add column if not exists core_weekly_hours numeric
  check (core_weekly_hours is null or (core_weekly_hours >= 0 and core_weekly_hours <= 168));
