-- 0063_tidy_link.sql — a link on a small task / deadline: any web address (an email in
-- Outlook on the web, a document, a form…), opened from the 🔗 beside it. Safe to re-run.
alter table tidy add column if not exists link text;
