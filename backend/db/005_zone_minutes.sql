-- Active Zone Minutes: minutes with a raised heart rate (harder zones count double). Google Health's weekly cardio goal.
ALTER TABLE daily_metrics ADD COLUMN IF NOT EXISTS zone_minutes int CHECK (zone_minutes >= 0);
