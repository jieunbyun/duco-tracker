-- 0071_tidy_repeat.sql — small tasks that repeat: every month, every year, or every year
-- on a date of the (Korean) lunar calendar. Run after 0063_tidy_link.sql and 0066_tidy_kind.sql.
--
-- tidy_repeat  a series: its title (and link, tidy-up), how it repeats and from when;
--              until: stopped, with nothing after that day
-- tidy         each date of a series is an ordinary small task, made when Week first shows
--              that day: repeat_id (its series) and repeat_on (the date it is for, kept when
--              the task is moved). One per series and date. Deleting one hides it (skipped),
--              so it is not made again; the series goes on.
--
-- Stopping a series keeps its tasks up to then. Undoing a series' start takes away the
-- tasks it made (on delete cascade); nothing else deletes a series.
--
-- Yours alone. Safe to re-run.
create table if not exists tidy_repeat (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null default auth.uid() references auth.users on delete cascade,
  title       text not null check (btrim(title) <> ''),
  every       text not null check (every in ('month', 'year', 'lunar_year')),
  month       smallint check (month between 1 and 12),          -- for a yearly one (lunar month for lunar_year)
  day         smallint not null check (day between 1 and 31),   -- the month's last day when it has fewer
  start_on    date not null,
  until       date,
  link        text,
  is_tidy     boolean not null default false,
  created_at  timestamptz not null default now(),
  check ((every = 'month') = (month is null))
);
create index if not exists tidy_repeat_of on tidy_repeat (user_id);

alter table tidy add column if not exists repeat_id uuid references tidy_repeat on delete cascade;
alter table tidy add column if not exists repeat_on date;
alter table tidy add column if not exists skipped boolean not null default false;
do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'tidy_repeat_once') then
    alter table tidy add constraint tidy_repeat_once unique (repeat_id, repeat_on);
  end if;
end $$;

alter table tidy_repeat enable row level security;
drop policy if exists owner_all on tidy_repeat;
create policy owner_all on tidy_repeat for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
grant select, insert, update, delete on table tidy_repeat to authenticated;

-- undo, for your own changes only (as 0052)
do $$
begin
  if to_regprocedure('log_change()') is not null then
    drop trigger if exists undo_log on tidy_repeat;
    create trigger undo_log after insert or update on tidy_repeat
      for each row when (new.user_id = auth.uid()) execute function log_change();
    drop trigger if exists undo_log_delete on tidy_repeat;
    create trigger undo_log_delete after delete on tidy_repeat
      for each row when (old.user_id = auth.uid()) execute function log_change();
  end if;
end $$;
