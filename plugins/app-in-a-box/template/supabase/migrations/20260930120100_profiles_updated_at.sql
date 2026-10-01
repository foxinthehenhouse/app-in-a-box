-- Keep profiles.updated_at honest: it had a default but nothing ever changed it.
-- clock_timestamp() (not now()) so an update in the same transaction as the insert
-- still moves it forward.
-- Rollback: drop trigger profiles_set_updated_at on public.profiles;
--           drop function public.set_updated_at();

create or replace function public.set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at := clock_timestamp();
  return new;
end;
$$;

drop trigger if exists profiles_set_updated_at on public.profiles;
create trigger profiles_set_updated_at
  before update on public.profiles
  for each row execute function public.set_updated_at();
