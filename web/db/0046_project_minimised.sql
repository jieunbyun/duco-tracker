-- 0046_project_minimised.sql — which shared projects each person keeps minimised
-- on their list: a preference of their own, kept with their account so it is
-- still there at the next log-on, from any computer. Safe to re-run.
create table if not exists project_minimised (
  user_id    uuid not null default auth.uid() references auth.users on delete cascade,
  project_id uuid not null references group_project on delete cascade,
  primary key (user_id, project_id)
);

alter table project_minimised enable row level security;
drop policy if exists mine on project_minimised;
create policy mine on project_minimised for all to authenticated
  using (user_id = auth.uid())
  with check (user_id = auth.uid());

grant select, insert, update, delete on table project_minimised to authenticated;
