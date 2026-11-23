-- 0059_diary.sql — Diary: your life, a line a day, and a look back each month.
--
-- diary_day    one a day: the happiest moment and why, the worst moment, each with a
--              life area (work, family, friends, health, self, other) and a star for
--              the ones that stand out, and the day's mood, 1–10
-- diary_month  one a month (its first day): your reflection on it
--
-- Yours alone: nobody else can read them, not even as supervisor. Safe to re-run.
create table if not exists diary_day (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null default auth.uid() references auth.users on delete cascade,
  day         date not null,
  mood        integer check (mood between 1 and 10),
  best        text,
  best_why    text,
  best_area   text,
  best_star   boolean not null default false,
  worst       text,
  worst_area  text,
  worst_star  boolean not null default false,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  unique (user_id, day)
);

create table if not exists diary_month (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null default auth.uid() references auth.users on delete cascade,
  month       date not null check (extract(day from month) = 1),
  reflection  text,
  updated_at  timestamptz not null default now(),
  unique (user_id, month)
);

alter table diary_day   enable row level security;
alter table diary_month enable row level security;
drop policy if exists owner_all on diary_day;
create policy owner_all on diary_day for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
drop policy if exists owner_all on diary_month;
create policy owner_all on diary_month for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
grant select, insert, update, delete on table diary_day, diary_month to authenticated;

-- undo, for your own changes only (as 0052)
do $$
declare t text;
begin
  if to_regprocedure('log_change()') is not null then
    foreach t in array array['diary_day', 'diary_month'] loop
      execute format('drop trigger if exists undo_log on %I', t);
      execute format('create trigger undo_log after insert or update on %I
                        for each row when (new.user_id = auth.uid()) execute function log_change()', t);
      execute format('drop trigger if exists undo_log_delete on %I', t);
      execute format('create trigger undo_log_delete after delete on %I
                        for each row when (old.user_id = auth.uid()) execute function log_change()', t);
    end loop;
  end if;
end $$;
