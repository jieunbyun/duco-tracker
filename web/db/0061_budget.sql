-- 0061_budget.sql — Budget: your grant and project budgets, in place of the spreadsheets.
--
-- budget          one grant or project: its total, currency, dates, and (if you like) the
--                 Planning project it pays for
-- budget_line     what the money is for (Marta's time, Conference…): its plan and account code
-- budget_expense  money spent: when, how much, on which line, and what for
--
-- "Used" and "Remaining" are never stored: they are added up from the expenses.
-- Yours alone. Safe to re-run.
create table if not exists budget (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null default auth.uid() references auth.users on delete cascade,
  name        text not null check (btrim(name) <> ''),
  total       numeric check (total is null or total >= 0),
  currency    text not null default '£',
  starts_on   date,
  ends_on     date,
  project_id  uuid references project on delete set null,
  notes       text,
  created_at  timestamptz not null default now(),
  unique (id, user_id)
);

create table if not exists budget_line (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null default auth.uid() references auth.users on delete cascade,
  budget_id   uuid not null,
  name        text not null check (btrim(name) <> ''),
  plan        numeric check (plan is null or plan >= 0),
  account     text,
  sort_order  integer not null default 0,
  created_at  timestamptz not null default now(),
  foreign key (budget_id, user_id) references budget (id, user_id) on delete cascade
);
create index if not exists budget_line_of on budget_line (budget_id, user_id, sort_order);

create table if not exists budget_expense (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null default auth.uid() references auth.users on delete cascade,
  budget_id   uuid not null,
  line_id     uuid references budget_line on delete set null,
  spent_on    date,
  amount      numeric not null,
  item        text,
  detail      text,
  created_at  timestamptz not null default now(),
  foreign key (budget_id, user_id) references budget (id, user_id) on delete cascade
);
create index if not exists budget_expense_of on budget_expense (budget_id, user_id, spent_on desc);

alter table budget         enable row level security;
alter table budget_line    enable row level security;
alter table budget_expense enable row level security;
do $$
declare t text;
begin
  foreach t in array array['budget', 'budget_line', 'budget_expense'] loop
    execute format('drop policy if exists owner_all on %I', t);
    execute format('create policy owner_all on %I for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid())', t);
    execute format('grant select, insert, update, delete on table %I to authenticated', t);
  end loop;
end $$;

-- undo, for your own changes only (as 0052)
do $$
declare t text;
begin
  if to_regprocedure('log_change()') is not null then
    foreach t in array array['budget', 'budget_line', 'budget_expense'] loop
      execute format('drop trigger if exists undo_log on %I', t);
      execute format('create trigger undo_log after insert or update on %I
                        for each row when (new.user_id = auth.uid()) execute function log_change()', t);
      execute format('drop trigger if exists undo_log_delete on %I', t);
      execute format('create trigger undo_log_delete after delete on %I
                        for each row when (old.user_id = auth.uid()) execute function log_change()', t);
    end loop;
  end if;
end $$;
