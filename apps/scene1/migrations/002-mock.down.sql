-- Isolated tests only; does not delete business rows. Remove migration version record only after manual approval.
ALTER TABLE simulation_rules DROP CHECK ck_simulation_ranges;
ALTER TABLE notification_jobs DROP CHECK ck_notification_count;
DROP INDEX ix_notifications_due ON notification_jobs;
