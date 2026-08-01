-- ============================================================
-- Internship Portal — Supabase (Postgres) schema
-- Run this once in Supabase: Project → SQL Editor → New query → paste → Run
-- No dummy/seed data is inserted. Every table starts empty.
-- ============================================================

create extension if not exists "uuid-ossp";

-- ---------- PROFILES (extends Supabase auth.users) ----------
create table if not exists profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  full_name text not null,
  role text not null default 'student' check (role in ('student','admin','mentor')),
  avatar_url text,
  created_at timestamptz not null default now()
);

-- Auto-create a profile row whenever someone signs up via Supabase Auth
create or replace function public.handle_new_user()
returns trigger as $$
begin
  insert into public.profiles (id, full_name, role)
  values (new.id, coalesce(new.raw_user_meta_data->>'full_name', new.email), 'student');
  return new;
end;
$$ language plpgsql security definer;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute procedure public.handle_new_user();

-- ---------- COURSES ----------
create table if not exists courses (
  id uuid primary key default uuid_generate_v4(),
  title text not null,
  description text,
  created_by uuid references profiles(id),
  is_published boolean not null default false,
  created_at timestamptz not null default now()
);

-- ---------- LESSONS ----------
create table if not exists lessons (
  id uuid primary key default uuid_generate_v4(),
  course_id uuid not null references courses(id) on delete cascade,
  title text not null,
  script text not null,                 -- the lesson script text (source for TTS + avatar)
  avatar_photo_url text,                -- presenter photo to use for this lesson (falls back to default)
  status text not null default 'draft'
    check (status in ('draft','approved','queued','rendering','ready','failed')),
  video_url text,                       -- filled in once SadTalker render completes
  order_index int not null default 0,
  created_by uuid references profiles(id),
  created_at timestamptz not null default now(),
  approved_at timestamptz
);

-- ---------- ENROLLMENTS ----------
create table if not exists enrollments (
  id uuid primary key default uuid_generate_v4(),
  student_id uuid not null references profiles(id) on delete cascade,
  course_id uuid not null references courses(id) on delete cascade,
  progress numeric not null default 0,   -- 0-100
  created_at timestamptz not null default now(),
  unique (student_id, course_id)
);

-- ---------- VIDEO RENDER JOB QUEUE ----------
-- This is the table your Colab/Kaggle SadTalker worker polls.
create table if not exists video_jobs (
  id uuid primary key default uuid_generate_v4(),
  lesson_id uuid not null references lessons(id) on delete cascade,
  status text not null default 'queued'
    check (status in ('queued','in_progress','done','failed')),
  script_text text not null,
  avatar_photo_url text,
  result_video_url text,
  error_message text,
  claimed_at timestamptz,
  claimed_by text,                      -- free-text worker identifier (e.g. "colab-worker-1")
  created_at timestamptz not null default now(),
  completed_at timestamptz
);

create index if not exists idx_video_jobs_status on video_jobs(status, created_at);

-- ---------- SUBMISSIONS ----------
create table if not exists submissions (
  id uuid primary key default uuid_generate_v4(),
  lesson_id uuid not null references lessons(id) on delete cascade,
  student_id uuid not null references profiles(id) on delete cascade,
  content text not null,
  status text not null default 'submitted'
    check (status in ('submitted','graded','flagged')),
  ai_score numeric,
  ai_feedback text,
  ai_provider text,                     -- which provider actually graded it (gemini / groq)
  created_at timestamptz not null default now(),
  graded_at timestamptz
);

-- ---------- MENTOR CHAT HISTORY ----------
create table if not exists mentor_messages (
  id uuid primary key default uuid_generate_v4(),
  student_id uuid not null references profiles(id) on delete cascade,
  role text not null check (role in ('user','assistant')),
  content text not null,
  created_at timestamptz not null default now()
);

-- ============================================================
-- ROW LEVEL SECURITY
-- Frontend uses the Supabase anon key + logged-in user JWT.
-- The Python backend uses the SERVICE ROLE key (bypasses RLS)
-- for admin actions and for the Colab worker endpoints.
-- ============================================================

alter table profiles enable row level security;
alter table courses enable row level security;
alter table lessons enable row level security;
alter table enrollments enable row level security;
alter table video_jobs enable row level security;
alter table submissions enable row level security;
alter table mentor_messages enable row level security;

-- profiles: users can read/update their own profile
create policy "read own profile" on profiles for select using (auth.uid() = id);
create policy "update own profile" on profiles for update using (auth.uid() = id);

-- courses: anyone logged in can read published courses
create policy "read published courses" on courses for select using (is_published = true);

-- lessons: students can only read lessons whose status is 'ready' (video rendered) or 'approved'
create policy "read visible lessons" on lessons for select using (status in ('approved','ready'));

-- enrollments: students see/manage only their own enrollment rows
create policy "read own enrollments" on enrollments for select using (auth.uid() = student_id);
create policy "insert own enrollment" on enrollments for insert with check (auth.uid() = student_id);

-- submissions: students see/insert only their own submissions
create policy "read own submissions" on submissions for select using (auth.uid() = student_id);
create policy "insert own submissions" on submissions for insert with check (auth.uid() = student_id);

-- mentor_messages: students see/insert only their own chat history
create policy "read own mentor messages" on mentor_messages for select using (auth.uid() = student_id);
create policy "insert own mentor messages" on mentor_messages for insert with check (auth.uid() = student_id);

-- video_jobs: no direct client access at all (backend service role only)
-- (no select/insert/update policy => only service role, which bypasses RLS, can touch this table)

-- ============================================================
-- STORAGE BUCKETS (create these in Supabase Dashboard → Storage)
--   1. "avatars"        — presenter photo(s), public read
--   2. "lesson-videos"  — rendered SadTalker output, public read
-- Set both to "public" bucket so <video>/<img> tags can load them directly.
-- ============================================================
