-- Users and their profile
CREATE TABLE IF NOT EXISTS users (
    id          bigserial PRIMARY KEY,
    name        text NOT NULL,
    email       text UNIQUE NOT NULL,
    age         int CHECK (age BETWEEN 13 AND 120),
    sex         text,
    height_cm   numeric(5,1),
    weight_kg   numeric(5,1),
    goal        text,
    timezone    text NOT NULL DEFAULT 'Asia/Kolkata',
    created_at  timestamptz DEFAULT now()
);

-- One row per night. "date" = the morning you woke up.
CREATE TABLE IF NOT EXISTS sleep_logs (
    user_id        bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date           date NOT NULL,
    bedtime        timestamptz NOT NULL,
    wake_time      timestamptz NOT NULL,
    total_minutes  int NOT NULL CHECK (total_minutes BETWEEN 0 AND 1440),
    deep_minutes   int,
    rem_minutes    int,
    light_minutes  int,
    awake_minutes  int,
    PRIMARY KEY (user_id, date)
);

-- One row per day: steps, calories, heart
CREATE TABLE IF NOT EXISTS daily_metrics (
    user_id         bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date            date NOT NULL,
    steps           int CHECK (steps >= 0),
    active_minutes  int,
    calories_out    int,
    resting_hr      int CHECK (resting_hr BETWEEN 25 AND 220),
    hrv_ms          numeric(5,1),
    PRIMARY KEY (user_id, date)
);

-- One row per workout
CREATE TABLE IF NOT EXISTS workouts (
    id                bigserial PRIMARY KEY,
    user_id           bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    started_at        timestamptz NOT NULL,
    type              text NOT NULL,          -- strength, run, walk, yoga
    name              text,                   -- e.g. "Leg day"
    duration_minutes  int NOT NULL CHECK (duration_minutes > 0),
    avg_hr            int,
    calories          int,
    UNIQUE (user_id, started_at)
);

CREATE INDEX IF NOT EXISTS workouts_user_time_idx ON workouts (user_id, started_at DESC);