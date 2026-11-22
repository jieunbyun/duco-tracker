-- 0052_failures.sql — Failures: general themes, and under each the hypotheses you
-- tried: the test, the lessons from failure, when it was created and its deadline.
-- A hypothesis can be on a Planning project or milestone, or on a shared one.
-- Yours alone: other people on a shared project do not see it. Safe to re-run.
create table if not exists failure_theme (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null default auth.uid() references auth.users on delete cascade,
  name        text not null check (btrim(name) <> ''),
  created_at  timestamptz not null default now(),
  unique (id, user_id)
);

create table if not exists failure (
  id                  uuid primary key default gen_random_uuid(),
  user_id             uuid not null default auth.uid() references auth.users on delete cascade,
  theme_id            uuid not null,
  hypothesis          text not null check (btrim(hypothesis) <> ''),
  test                text,
  lesson              text,
  created_on          date not null default current_date,
  due_on              date,
  project_id          uuid references project on delete set null,
  milestone_id        uuid references milestone on delete set null,
  -- No foreign keys on these two, on purpose: others on a shared project can delete its
  -- milestones, and a cascade into this row would copy it into their undo log (which they
  -- can read). It also means the link works again when what was deleted is restored.
  group_project_id    uuid,
  group_milestone_id  uuid,
  created_at          timestamptz not null default now(),
  -- only under your own theme, and a theme goes only once it is empty
  foreign key (theme_id, user_id) references failure_theme (id, user_id)
);
create index if not exists failure_theme_of on failure (theme_id, user_id);
create index if not exists failure_project on failure (project_id);
create index if not exists failure_milestone on failure (milestone_id);

alter table failure_theme enable row level security;
alter table failure       enable row level security;
drop policy if exists owner_all on failure_theme;
create policy owner_all on failure_theme for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
drop policy if exists owner_all on failure;
create policy owner_all on failure for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());

grant select, insert, update, delete on table failure_theme, failure to authenticated;

-- undo, for your own changes only: a row never goes into someone else's log
do $$
declare t text;
begin
  if to_regprocedure('log_change()') is not null then
    foreach t in array array['failure_theme', 'failure'] loop
      execute format('drop trigger if exists undo_log on %I', t);
      execute format('create trigger undo_log after insert or update on %I
                        for each row when (new.user_id = auth.uid()) execute function log_change()', t);
      execute format('drop trigger if exists undo_log_delete on %I', t);
      execute format('create trigger undo_log_delete after delete on %I
                        for each row when (old.user_id = auth.uid()) execute function log_change()', t);
    end loop;
  end if;
end $$;
