-- 0012_grants.sql — a Grant writing lane on the Pathways map. A grant is an
-- item of its own (writing period up to its deadline, where it stands, the
-- amount sought) that "funds" projects, people or objectives in other lanes;
-- until it is awarded, what it funds is shown as uncertain.
alter table pw_node drop constraint if exists pw_node_kind_check;
alter table pw_node add constraint pw_node_kind_check
  check (kind in ('goal', 'objective', 'project', 'person', 'gap', 'grant'));

alter table pw_node drop constraint if exists pw_node_lane_check;
alter table pw_node add constraint pw_node_lane_check
  check (lane in ('research', 'teaching', 'outreach', 'supervision', 'grants'));

alter table pw_node add column if not exists grant_stage text
  check (grant_stage in ('drafting', 'submitted', 'awarded', 'declined'));

alter table pw_link drop constraint if exists pw_link_kind_check;
alter table pw_link add constraint pw_link_kind_check
  check (kind in ('feeds', 'advances', 'works_on', 'learns', 'funds'));
