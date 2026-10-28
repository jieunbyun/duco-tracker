-- 0044_idea_notes.sql — an idea ("To think about") can carry several notes, each
-- dated, added as the thought develops. An idea's single note, if it has one,
-- becomes its first. Safe to re-run.
create table if not exists idea_note (
  id          uuid primary key default gen_random_uuid(),
  todo_id     uuid not null references todo on delete cascade,
  user_id     uuid not null default auth.uid() references auth.users on delete cascade,
  body        text not null check (btrim(body) <> ''),
  created_at  timestamptz not null default now()
);
create index if not exists idea_note_todo on idea_note (todo_id, created_at);

-- yours, on your own ideas
alter table idea_note enable row level security;
drop policy if exists mine on idea_note;
create policy mine on idea_note for all to authenticated
  using (user_id = auth.uid())
  with check (user_id = auth.uid() and exists (select 1 from todo t where t.id = todo_id and t.user_id = auth.uid()));

grant select, insert, update, delete on table idea_note to authenticated;

do $$
begin
  if to_regprocedure('log_change()') is not null then
    drop trigger if exists undo_log on idea_note;
    create trigger undo_log after insert or update or delete on idea_note
      for each row execute function log_change();
  end if;
end $$;

-- the single notes so far become first notes (dated when the idea was jotted down)
insert into idea_note (todo_id, user_id, body, created_at)
select id, user_id, note, created_at from todo
where kind = 'idea' and note is not null and btrim(note) <> '';
update todo set note = null where kind = 'idea' and note is not null;
