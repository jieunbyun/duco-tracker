-- 0060_meetings.sql — Meetings: your meeting logs, as your .tex files kept them.
--
-- meeting_series  one log (one file): a name, the headings its meetings start with,
--                 and, if you like, the Planning project it belongs to
-- meeting         one meeting (one \section*): the date, a title, who was there, and its
--                 sections in order, kept with it as
--                   [{ "heading", "body", "closed": bool, "sent": [lines sent to Week] }]
--                 ("closed": an Open question you have ticked off)
--
-- Yours alone: notes on people (interviews, students) are not seen by anyone else,
-- not even on a shared project. Safe to re-run.
create table if not exists meeting_series (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null default auth.uid() references auth.users on delete cascade,
  name        text not null check (btrim(name) <> ''),
  headings    text[] not null default '{}',
  project_id  uuid references project on delete set null,
  created_at  timestamptz not null default now(),
  unique (id, user_id)
);

create table if not exists meeting (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null default auth.uid() references auth.users on delete cascade,
  series_id   uuid not null,
  met_on      date not null default current_date,
  title       text,
  people      text,
  sections    jsonb not null default '[]'::jsonb check (jsonb_typeof(sections) = 'array'),
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  -- only under your own series, and goes with it
  foreign key (series_id, user_id) references meeting_series (id, user_id) on delete cascade
);
create index if not exists meeting_of on meeting (series_id, user_id, met_on desc);

alter table meeting_series enable row level security;
alter table meeting        enable row level security;
drop policy if exists owner_all on meeting_series;
create policy owner_all on meeting_series for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
drop policy if exists owner_all on meeting;
create policy owner_all on meeting for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
grant select, insert, update, delete on table meeting_series, meeting to authenticated;

-- undo, for your own changes only (as 0052)
do $$
declare t text;
begin
  if to_regprocedure('log_change()') is not null then
    foreach t in array array['meeting_series', 'meeting'] loop
      execute format('drop trigger if exists undo_log on %I', t);
      execute format('create trigger undo_log after insert or update on %I
                        for each row when (new.user_id = auth.uid()) execute function log_change()', t);
      execute format('drop trigger if exists undo_log_delete on %I', t);
      execute format('create trigger undo_log_delete after delete on %I
                        for each row when (old.user_id = auth.uid()) execute function log_change()', t);
    end loop;
  end if;
end $$;
