-- AI Frontier Quest: accounts and synced progress.
-- One row per signed-up user. Row Level Security limits every user to their own row.

create table if not exists public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  display_name text check (char_length(display_name) <= 60),
  persona text check (persona in ('student', 'engineer', 'researcher', 'leader')),
  interests text[] not null default '{}',
  daily_goal integer not null default 100 check (daily_goal between 20 and 500),
  progress jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.profiles enable row level security;

drop policy if exists "Users read own profile" on public.profiles;
drop policy if exists "Users insert own profile" on public.profiles;
drop policy if exists "Users update own profile" on public.profiles;
drop policy if exists "Users delete own profile" on public.profiles;

create policy "Users read own profile" on public.profiles
  for select to authenticated using ((select auth.uid()) = id);
create policy "Users insert own profile" on public.profiles
  for insert to authenticated with check ((select auth.uid()) = id);
create policy "Users update own profile" on public.profiles
  for update to authenticated using ((select auth.uid()) = id) with check ((select auth.uid()) = id);
create policy "Users delete own profile" on public.profiles
  for delete to authenticated using ((select auth.uid()) = id);

revoke all on public.profiles from anon;
grant select, insert, update, delete on public.profiles to authenticated;

-- Keep updated_at current.
create or replace function public.touch_updated_at()
returns trigger language plpgsql set search_path = '' as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

drop trigger if exists profiles_touch on public.profiles;
create trigger profiles_touch before update on public.profiles
  for each row execute function public.touch_updated_at();

-- Create the profile row automatically at sign-up, using the name given on the sign-up form.
create or replace function public.handle_new_user()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  insert into public.profiles (id, display_name)
  values (new.id, left(coalesce(new.raw_user_meta_data ->> 'display_name', split_part(new.email, '@', 1)), 60))
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users
  for each row execute function public.handle_new_user();
