-- Run this in Supabase SQL editor to initialize the schema

-- ============================================================
-- services — service catalogue
-- ============================================================
create table if not exists services (
    id            uuid primary key default gen_random_uuid(),
    name          text not null,
    duration_min  integer not null default 60,
    price         integer not null default 0,
    is_active     boolean not null default true
);

-- Seed initial services
insert into services (name, duration_min, price) values
    ('Наращивание ресниц (классика)',   120, 2500),
    ('Наращивание ресниц (объём)',      150, 3500),
    ('Коррекция ресниц',               90,  2000),
    ('Снятие ресниц',                  30,  500),
    ('Биозавивка ресниц',              90,  2500)
on conflict do nothing;

-- ============================================================
-- slots — master's working slots
-- ============================================================
create table if not exists slots (
    id                uuid primary key default gen_random_uuid(),
    slot_date         date not null,
    slot_time         time not null,
    status            text not null default 'free' check (status in ('free', 'busy')),
    calendar_event_id text,
    created_at        timestamptz not null default now(),
    unique (slot_date, slot_time)
);

-- ============================================================
-- bookings — client appointments
-- ============================================================
create table if not exists bookings (
    id                  uuid primary key default gen_random_uuid(),
    telegram_id         bigint not null,
    client_name         text not null,
    client_phone        text not null,
    service_id          uuid references services(id),
    slot_id             uuid references slots(id),
    status              text not null default 'active' check (status in ('active', 'cancelled', 'completed')),
    calendar_event_id   text,
    reminder_24h_sent   boolean not null default false,
    reminder_2h_sent    boolean not null default false,
    created_at          timestamptz not null default now()
);

-- Indexes for common queries
create index if not exists idx_bookings_telegram_id on bookings(telegram_id);
create index if not exists idx_bookings_status      on bookings(status);
create index if not exists idx_slots_date_status    on slots(slot_date, status);
