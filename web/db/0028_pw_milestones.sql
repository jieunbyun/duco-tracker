-- 0028_pw_milestones.sql — a Pathways item linked to a Planning project can
-- show that project's milestones on its bar. They are read from Planning each
-- time, never copied, so they stay in step.
alter table pw_node add column if not exists show_milestones boolean not null default false;
