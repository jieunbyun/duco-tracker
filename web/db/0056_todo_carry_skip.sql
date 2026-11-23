-- 0056_todo_carry_skip.sql — Drop, in "Carry forward unfinished to-dos": a to-do left
-- where it is, open (neither done nor cancelled), but no longer offered for carrying
-- forward. It is listed apart, under "Dropped", to bring forward or put back later.
-- Filing it under another week (moving it, or carrying it forward) offers it again.
-- Safe to re-run.
alter table todo add column if not exists carry_skip boolean not null default false;

create or replace function todo_carry_skip_reset() returns trigger
language plpgsql set search_path = public as $$
begin
  -- moved to another week, by a change that did not itself drop or put it back
  -- (so an undo, which writes the flag as it was, keeps it)
  if new.due_on is distinct from old.due_on and new.carry_skip = old.carry_skip then
    new.carry_skip := false;
  end if;
  return new;
end $$;

drop trigger if exists todo_carry_skip_reset on todo;
create trigger todo_carry_skip_reset before update on todo
  for each row execute function todo_carry_skip_reset();
