-- Isolated tests only; does not delete business rows. Remove migration version record only after manual approval.
ALTER TABLE inventory_ledger DROP CHECK ck_inventory_balances;
ALTER TABLE inventory_ledger DROP CHECK ck_inventory_vectors;
ALTER TABLE demo_clock DROP CHECK ck_demo_clock;
ALTER TABLE outbox_jobs DROP CHECK ck_job_attempts;
ALTER TABLE refund_attempts DROP CHECK ck_refund_attempt_no;
ALTER TABLE idempotency_records DROP CHECK ck_idempotent_http;
ALTER TABLE products DROP CHECK ck_product_version;
ALTER TABLE orders DROP CHECK ck_order_version;
ALTER TABLE refund_applications DROP CHECK ck_review_fields;
DROP INDEX ix_orders_buyer_time ON orders;
DROP INDEX ix_orders_expiry ON orders;
DROP INDEX ix_jobs_due ON outbox_jobs;
DROP INDEX ix_anomalies_status ON payment_anomalies;
