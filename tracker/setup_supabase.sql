-- Run this in Supabase Dashboard → SQL Editor

create table if not exists jobs (
  id uuid primary key default gen_random_uuid(),
  company text,
  role text,
  url text unique,
  source text,
  snippet text,
  location text,
  date_found date,
  score float,
  work_auth_ok boolean default true,
  status text default 'found',
  cover_letter_path text,
  notes text,
  date_applied date,
  created_at timestamptz default now()
);

-- Index for fast deduplication lookups
create index if not exists jobs_url_idx on jobs (url);

-- Index for fetching pending jobs by score
create index if not exists jobs_status_score_idx on jobs (status, score desc);

-- Add application_data column for storing planned Easy Apply answers
alter table jobs add column if not exists application_data jsonb;

-- pending_approval: apply command has been sent, awaiting go confirmation
-- (valid status values: found, rejected, low_score, skipped, applied, pending_approval)
