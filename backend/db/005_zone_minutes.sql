-- Cardio minutes: time with a raised heart rate, where minutes in the harder zones count double.
-- Adds up to Google Health's weekly cardio figure.
ALTER TABLE daily_metrics ADD COLUMN IF NOT EXISTS zone_minutes int CHECK (zone_minutes >= 0);
