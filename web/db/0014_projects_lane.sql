-- 0014_projects_lane.sql — the Supervision lane becomes Projects: the home of
-- the smaller projects (yours, your students', your collaborators') that feed
-- into an objective or a goal. And a project can be marked hands-on: one your
-- own research time goes into substantially.
alter table pw_node drop constraint if exists pw_node_lane_check;
update pw_node set lane = 'projects' where lane = 'supervision';
alter table pw_node add constraint pw_node_lane_check
  check (lane in ('research', 'projects', 'teaching', 'outreach', 'grants'));

alter table pw_node add column if not exists hands_on boolean not null default false;
