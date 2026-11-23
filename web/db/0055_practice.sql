-- 0055_practice.sql — Practice: reading, writing and speaking, practised day by day.
-- A practice has a goal and may run over several days; each session under it is one
-- skill on one day, with your own feedback: what went well, what to fix, the focus for
-- next time, and 1–5 ratings on that skill's criteria, kept as { "criterion": n }.
-- Yours alone. Safe to re-run.
create table if not exists practice (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null default auth.uid() references auth.users on delete cascade,
  title       text not null check (btrim(title) <> ''),
  goal        text,
  started_on  date not null default current_date,
  done_on     date,                -- finished on; null while active
  created_at  timestamptz not null default now(),
  unique (id, user_id)
);
create index if not exists practice_user on practice (user_id, started_on desc);

create table if not exists practice_session (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null default auth.uid() references auth.users on delete cascade,
  practice_id  uuid not null,
  done_on      date not null default current_date,
  skill        text not null check (skill in ('reading', 'writing', 'speaking')),
  minutes      integer check (minutes is null or minutes >= 0),
  did          text,
  went_well    text,
  to_fix       text,
  next_focus   text,
  ratings      jsonb not null default '{}'::jsonb check (jsonb_typeof(ratings) = 'object'),
  created_at   timestamptz not null default now(),
  -- only under your own practice, and goes with it
  foreign key (practice_id, user_id) references practice (id, user_id) on delete cascade
);
create index if not exists practice_session_of on practice_session (practice_id, user_id, done_on);

alter table practice         enable row level security;
alter table practice_session enable row level security;
drop policy if exists owner_all on practice;
create policy owner_all on practice for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
drop policy if exists owner_all on practice_session;
create policy owner_all on practice_session for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());

grant select, insert, update, delete on table practice, practice_session to authenticated;

-- undo, for your own changes only (as 0052)
do $$
declare t text;
begin
  if to_regprocedure('log_change()') is not null then
    foreach t in array array['practice', 'practice_session'] loop
      execute format('drop trigger if exists undo_log on %I', t);
      execute format('create trigger undo_log after insert or update on %I
                        for each row when (new.user_id = auth.uid()) execute function log_change()', t);
      execute format('drop trigger if exists undo_log_delete on %I', t);
      execute format('create trigger undo_log_delete after delete on %I
                        for each row when (old.user_id = auth.uid()) execute function log_change()', t);
    end loop;
  end if;
end $$;
