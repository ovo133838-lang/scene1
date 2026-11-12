ALTER TABLE simulation_rules ADD CONSTRAINT ck_simulation_ranges CHECK (delay_ms BETWEEN 0 AND 600000 AND repeat_count BETWEEN 1 AND 20 AND remaining_uses BETWEEN 0 AND 20 AND (attempt_no IS NULL OR attempt_no>=1));
ALTER TABLE notification_jobs ADD CONSTRAINT ck_notification_count CHECK (remaining_deliveries BETWEEN 0 AND 20);
ALTER TABLE simulation_rules ALTER delay_ms SET DEFAULT 0;
ALTER TABLE simulation_rules ALTER repeat_count SET DEFAULT 1;
ALTER TABLE simulation_rules ALTER remaining_uses SET DEFAULT 1;
CREATE INDEX ix_notifications_due ON notification_jobs(status,deliver_after);
