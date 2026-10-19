-- 0006_outlook_range.sql — how far ahead Outlook events are brought in, in
-- weeks from the start of the current week (1 = this week only).
alter table calendar_feed
  add column if not exists sync_weeks smallint not null default 1 check (sync_weeks between 1 and 13);
