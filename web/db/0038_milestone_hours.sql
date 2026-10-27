-- 0038_milestone_hours.sql — the hours you plan to put into a shared project's
-- milestone are yours alone: each person on the project sets their own figure
-- for any milestone they can see, and nobody else (you included, for a
-- member's) sees it. Safe to re-run.
create table if not exists group_milestone_hours (
  milestone_id  uuid not null references group_milestone on delete cascade,
  user_id       uuid not null default auth.uid() references auth.users on delete cascade,
  planned_hours numeric not null check (planned_hours >= 0),
  primary key (milestone_id, user_id)
);

alter table group_milestone_hours enable row level security;
drop policy if exists mine on group_milestone_hours;
create policy mine on group_milestone_hours for all to authenticated
  using (user_id = auth.uid())
  with check (user_id = auth.uid() and sees_milestone(milestone_id));

grant select, insert, update, delete on table group_milestone_hours to authenticated;

do $$
begin
  if to_regprocedure('log_change()') is not null then
    drop trigger if exists undo_log on group_milestone_hours;
    create trigger undo_log after insert or update or delete on group_milestone_hours
      for each row execute function log_change();
  end if;
end $$;
