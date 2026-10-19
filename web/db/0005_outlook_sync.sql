-- 0005_outlook_sync.sql — bring Outlook events into the plan, for review.
--
-- calendar_feed    your published Outlook calendar link (private: whoever has
--                  it can read your calendar) and when it was last synced
-- calendar_ignore  events marked irrelevant: one occurrence, or (occurrence
--                  null) every occurrence of a repeating event
-- todo.source_*    where a to-do came from, and Outlook's own date and times
--                  as last seen, so a later sync can tell what Outlook changed
-- todo.reviewed    false until you keep it; unreviewed events wait in Week's
--                  "From Outlook" list and do not count as planned time

create table calendar_feed (
  user_id         uuid primary key default auth.uid() references auth.users on delete cascade,
  ics_url         text,
  last_synced_at  timestamptz,
  last_status     text
);

create table calendar_ignore (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null default auth.uid() references auth.users on delete cascade,
  uid         text not null,
  occurrence  text,
  title       text,
  created_at  timestamptz not null default now()
);
create unique index calendar_ignore_once on calendar_ignore (user_id, uid, coalesce(occurrence, ''));

alter table todo
  add column source          text check (source in ('outlook')),
  add column source_key      text,
  add column source_uid      text,
  add column source_date     date,
  add column source_start    time,
  add column source_end      time,
  add column source_free     boolean not null default false,
  add column source_all_day  boolean not null default false,
  add column reviewed        boolean not null default true;
create unique index todo_source_key on todo (user_id, source_key) where source_key is not null;

alter table calendar_feed   enable row level security;
alter table calendar_ignore enable row level security;
create policy owner_all on calendar_feed   for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy owner_all on calendar_ignore for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
