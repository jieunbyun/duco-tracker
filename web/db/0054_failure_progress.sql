-- 0054_failure_progress.sql — a hypothesis's progress: ticked complete (the date it
-- was completed, null while ongoing), and its observations and calibrations — dated
-- notes added as the work goes on, like an action's comments in the Logbook.
-- Yours alone, like the hypothesis. Safe to re-run.
alter table failure add column if not exists done_on date;

-- a note goes only under your own hypothesis (and with it)
do $$
begin
  alter table failure add constraint failure_id_user unique (id, user_id);
exception when duplicate_table or duplicate_object then null;
end $$;

create table if not exists failure_note (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null default auth.uid() references auth.users on delete cascade,
  failure_id  uuid not null,
  kind        text not null default 'observation' check (kind in ('observation', 'calibration')),
  noted_on    date not null default current_date,
  body        text not null check (btrim(body) <> ''),
  created_at  timestamptz not null default now(),
  foreign key (failure_id, user_id) references failure (id, user_id) on delete cascade
);
create index if not exists failure_note_of on failure_note (failure_id, user_id, noted_on);

alter table failure_note enable row level security;
drop policy if exists owner_all on failure_note;
create policy owner_all on failure_note for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
grant select, insert, update, delete on table failure_note to authenticated;

-- undo, for your own changes only (as 0052)
do $$
begin
  if to_regprocedure('log_change()') is not null then
    drop trigger if exists undo_log on failure_note;
    create trigger undo_log after insert or update on failure_note
      for each row when (new.user_id = auth.uid()) execute function log_change();
    drop trigger if exists undo_log_delete on failure_note;
    create trigger undo_log_delete after delete on failure_note
      for each row when (old.user_id = auth.uid()) execute function log_change();
  end if;
end $$;
