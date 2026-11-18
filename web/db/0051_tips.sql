-- 0051_tips.sql — Tips: checklists you keep by topic ("Submitting a paper",
-- "Before a site visit"…), each with a category of your own and notes, and found
-- again by searching as you type. A topic's checklist is kept with it, in order,
-- as [{ "id", "text", "done" }]. Yours alone. Safe to re-run.
create table if not exists tip (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null default auth.uid() references auth.users on delete cascade,
  title       text not null check (btrim(title) <> ''),
  category    text,
  notes       text,
  items       jsonb not null default '[]'::jsonb check (jsonb_typeof(items) = 'array'),
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
create index if not exists tip_user on tip (user_id, updated_at desc);

alter table tip enable row level security;
drop policy if exists owner_all on tip;
create policy owner_all on tip for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());

grant select, insert, update, delete on table tip to authenticated;

do $$
begin
  if to_regprocedure('log_change()') is not null then
    drop trigger if exists undo_log on tip;
    create trigger undo_log after insert or update or delete on tip
      for each row execute function log_change();
  end if;
end $$;
