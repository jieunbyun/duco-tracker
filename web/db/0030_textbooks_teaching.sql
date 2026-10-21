-- 0030_textbooks_teaching.sql — Textbooks belong to Teaching, not Research.
-- The category moves with its projects and logged time, so past textbook hours
-- count towards Teaching too. Safe to re-run.
update category c
set area_id = a.id, code = 'TEA_TEXT', sort_order = 70
from area a
where a.user_id = c.user_id and a.code = 'TEA'
  and c.code = 'RES_TEXT';
