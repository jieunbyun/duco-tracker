-- 0076_pw_experiments.sql — Experiments (0066) linked to items on Pathways: a topic or subtopic
-- can be on any number of items, and an item can have any number of them. Shown and added to in
-- the item's Experiments tab, at the side of the map. Yours alone.
-- Run after 0010_pathways.sql and 0066_experiments.sql. Safe to re-run.
create table if not exists pw_experiment (
  user_id     uuid not null default auth.uid() references auth.users on delete cascade,
  node_id     uuid not null references pw_node on delete cascade,
  topic_id    uuid not null references exp_topic on delete cascade,
  created_at  timestamptz not null default now(),
  primary key (node_id, topic_id)
);
create index if not exists pw_experiment_topic on pw_experiment (topic_id);

alter table pw_experiment enable row level security;
drop policy if exists owner_all on pw_experiment;
create policy owner_all on pw_experiment for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
grant select, insert, update, delete on table pw_experiment to authenticated;

-- undo, for your own changes only (as 0066)
do $$
begin
  if to_regprocedure('log_change()') is not null then
    drop trigger if exists undo_log on pw_experiment;
    create trigger undo_log after insert or update on pw_experiment
      for each row when (new.user_id = auth.uid()) execute function log_change();
    drop trigger if exists undo_log_delete on pw_experiment;
    create trigger undo_log_delete after delete on pw_experiment
      for each row when (old.user_id = auth.uid()) execute function log_change();
  end if;
end $$;
