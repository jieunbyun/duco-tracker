-- 0058_tidy.sql — Tidy-ups, in Week: small daily tasks with no hours — a checkbox and a
-- few words on a day ("Clear the desk", "Empty the downloads folder"). Ticked off, moved
-- to another day, renamed or deleted; never counted as planned or logged time.
-- Yours alone. Safe to re-run.
create table if not exists tidy (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null default auth.uid() references auth.users on delete cascade,
  day         date not null,
  title       text not null check (btrim(title) <> ''),
  is_done     boolean not null default false,
  sort_order  integer,
  created_at  timestamptz not null default now()
);
create index if not exists tidy_user_day on tidy (user_id, day);

alter table tidy enable row level security;
drop policy if exists owner_all on tidy;
create policy owner_all on tidy for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
grant select, insert, update, delete on table tidy to authenticated;

-- undo, for your own changes only (as 0052)
do $$
begin
  if to_regprocedure('log_change()') is not null then
    drop trigger if exists undo_log on tidy;
    create trigger undo_log after insert or update on tidy
      for each row when (new.user_id = auth.uid()) execute function log_change();
    drop trigger if exists undo_log_delete on tidy;
    create trigger undo_log_delete after delete on tidy
      for each row when (old.user_id = auth.uid()) execute function log_change();
  end if;
end $$;
