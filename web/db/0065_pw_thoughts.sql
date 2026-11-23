-- 0065_pw_thoughts.sql — Thoughts on a Pathways goal: dated notes, each still valid or no
-- longer valid (when, and why), all kept with the goal. Yours alone. Safe to re-run.
create table if not exists pw_thought (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null default auth.uid() references auth.users on delete cascade,
  node_id     uuid not null references pw_node on delete cascade,
  noted_on    date not null default current_date,
  body        text not null check (btrim(body) <> ''),
  valid       boolean not null default true,
  invalid_on  date,        -- when it stopped holding
  why         text,        -- and why
  created_at  timestamptz not null default now()
);
create index if not exists pw_thought_of on pw_thought (node_id, noted_on desc);

alter table pw_thought enable row level security;
drop policy if exists owner_all on pw_thought;
create policy owner_all on pw_thought for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
grant select, insert, update, delete on table pw_thought to authenticated;

-- undo, for your own changes only (as 0052)
do $$
begin
  if to_regprocedure('log_change()') is not null then
    drop trigger if exists undo_log on pw_thought;
    create trigger undo_log after insert or update on pw_thought
      for each row when (new.user_id = auth.uid()) execute function log_change();
    drop trigger if exists undo_log_delete on pw_thought;
    create trigger undo_log_delete after delete on pw_thought
      for each row when (old.user_id = auth.uid()) execute function log_change();
  end if;
end $$;
