-- 0003_drop_life.sql — the tracker is work-only; life areas are retired.
--
-- Removes any life areas/categories (and anything logged or planned against
-- them, should an earlier import have added some), then drops area.domain.
-- Safe to run whether or not life rows exist.

delete from todo
where category_id in (select c.id from category c join area a on a.id = c.area_id
                      where a.domain = 'life');
delete from time_entry
where category_id in (select c.id from category c join area a on a.id = c.area_id
                      where a.domain = 'life');
delete from category
where area_id in (select id from area where domain = 'life');
delete from area_target
where area_id in (select id from area where domain = 'life');
delete from area where domain = 'life';

drop view entry_hours;
alter table area drop column domain;

create view entry_hours with (security_invoker = true) as
select e.id,
       e.started_at,
       (e.started_at at time zone 'UTC')::date as entry_date,
       e.minutes / 60.0 as hours,
       e.is_core,
       e.description,
       a.id  as area_id,      a.label as area_label,
       c.id  as category_id,  c.label as category_label, c.kind as category_kind,
       p.id  as project_id,   p.name  as project_name,
       m.id  as milestone_id, m.title as milestone_title
from time_entry e
join category c on c.id = e.category_id
join area a     on a.id = c.area_id
left join project p   on p.id = e.project_id
left join milestone m on m.id = e.milestone_id;
