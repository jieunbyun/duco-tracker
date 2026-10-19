-- 0008_reading.sql — what you read: journals, books and more, with dated
-- notes, citation details, the reading period, and an optional PDF.
--
-- reading        one item: kind, bibliographic details, status and period
-- reading_note   dated notes on an item (optionally a page)
-- storage bucket "reading-pdfs": private; each user's files sit in a folder
--                named by their user id, and only they can read or write it

create table reading (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null default auth.uid() references auth.users on delete cascade,
  kind         text not null default 'article' check (kind in ('article', 'book', 'chapter', 'report', 'other')),
  title        text not null,
  authors      text,                 -- "Surname, Given; Surname, Given"
  year         integer,
  venue        text,                 -- journal, or the book a chapter is in
  publisher    text,
  volume       text,
  issue        text,
  pages        text,
  doi          text,
  url          text,
  citation     text,                 -- your own citation, used instead of the generated one
  status       text not null default 'to_read' check (status in ('to_read', 'reading', 'finished', 'abandoned')),
  started_on   date,
  finished_on  date,
  project_id   uuid references project on delete set null,
  pdf_path     text,                 -- path in the reading-pdfs bucket
  pdf_size     bigint,
  created_at   timestamptz not null default now(),
  check (finished_on is null or started_on is null or finished_on >= started_on)
);

create table reading_note (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null default auth.uid() references auth.users on delete cascade,
  reading_id  uuid not null references reading on delete cascade,
  noted_on    date not null default current_date,
  page        text,
  body        text not null,
  created_at  timestamptz not null default now()
);

create index on reading (user_id, status);
create index on reading_note (reading_id, noted_on);

alter table reading      enable row level security;
alter table reading_note enable row level security;
create policy owner_all on reading      for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy owner_all on reading_note for all to authenticated using (user_id = auth.uid()) with check (user_id = auth.uid());

-- private file storage for PDFs (50 MB a file)
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('reading-pdfs', 'reading-pdfs', false, 52428800, array['application/pdf'])
on conflict (id) do nothing;

create policy "reading pdfs: own folder, read" on storage.objects for select to authenticated
  using (bucket_id = 'reading-pdfs' and (storage.foldername(name))[1] = auth.uid()::text);
create policy "reading pdfs: own folder, add" on storage.objects for insert to authenticated
  with check (bucket_id = 'reading-pdfs' and (storage.foldername(name))[1] = auth.uid()::text);
create policy "reading pdfs: own folder, replace" on storage.objects for update to authenticated
  using (bucket_id = 'reading-pdfs' and (storage.foldername(name))[1] = auth.uid()::text);
create policy "reading pdfs: own folder, remove" on storage.objects for delete to authenticated
  using (bucket_id = 'reading-pdfs' and (storage.foldername(name))[1] = auth.uid()::text);
