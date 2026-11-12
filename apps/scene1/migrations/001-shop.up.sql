CREATE TABLE IF NOT EXISTS `accounts` (
`id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
`login_name` varchar(64) NOT NULL,
`password_hash` text NOT NULL,
`display_name` varchar(80) NOT NULL,
`role` varchar(16) NOT NULL,
CHECK (`role` IN('BUYER','OPERATOR','WAREHOUSE','SUPPORT')),
`enabled` boolean NOT NULL,
`created_at` datetime(6) NOT NULL,
`updated_at` datetime(6) NOT NULL,
PRIMARY KEY (`id`),
UNIQUE (`login_name`),
INDEX (`created_at`)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS `sessions` (
`id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
`account_id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
`token_hash` char(64) NOT NULL,
`expires_at` datetime(6) NOT NULL,
`revoked_at` datetime(6) NULL,
`created_at` datetime(6) NOT NULL,
PRIMARY KEY (`id`),
UNIQUE (`token_hash`),
INDEX (`created_at`),
INDEX (`expires_at`)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS `products` (
`id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
`sku` varchar(32) NOT NULL,
`name` varchar(120) NOT NULL,
`unit_price_cents` bigint NOT NULL,
`sale_status` varchar(16) NOT NULL,
CHECK (`sale_status` IN('ON_SHELF','OFF_SHELF')),
`initial_quantity` bigint NOT NULL,
`available_quantity` bigint NOT NULL,
`reserved_quantity` bigint NOT NULL,
`shipped_quantity` bigint NOT NULL,
`adjustment_net` bigint NOT NULL,
`version` bigint NOT NULL,
`created_at` datetime(6) NOT NULL,
`updated_at` datetime(6) NOT NULL,
PRIMARY KEY (`id`),
UNIQUE (`sku`),
CHECK (unit_price_cents BETWEEN 1 AND 1000000000),
CHECK (initial_quantity BETWEEN 0 AND 1000000),
CHECK (available_quantity BETWEEN 0 AND 1000000),
CHECK (reserved_quantity>=0),
CHECK (shipped_quantity>=0),
CHECK (initial_quantity+adjustment_net=available_quantity+reserved_quantity+shipped_quantity),
INDEX (`created_at`)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS `orders` (
`id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
`order_no` varchar(40) NOT NULL,
`buyer_id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
`product_id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
`sku_snapshot` varchar(32) NOT NULL,
`name_snapshot` varchar(120) NOT NULL,
`unit_price_cents` bigint NOT NULL,
`quantity` smallint NOT NULL,
`amount_cents` bigint NOT NULL,
CHECK (`amount_cents`>0),
`status` varchar(24) NOT NULL,
CHECK (`status` IN('PENDING_PAYMENT','CLOSED','PENDING_SHIPMENT','REFUND_REVIEW','REFUND_PROCESSING','REFUNDED','SHIPPED')),
`normal_receipt_id` char(36) CHARACTER SET ascii COLLATE ascii_bin NULL,
`active_application_id` char(36) CHARACTER SET ascii COLLATE ascii_bin NULL,
`close_reason` varchar(24) NULL,
CHECK (`close_reason` IN('BUYER_CANCELLED','TIMEOUT')),
`expires_at` datetime(6) NOT NULL,
`paid_at` datetime(6) NULL,
`closed_at` datetime(6) NULL,
`refunded_at` datetime(6) NULL,
`shipped_at` datetime(6) NULL,
`version` bigint NOT NULL,
`created_at` datetime(6) NOT NULL,
`updated_at` datetime(6) NOT NULL,
PRIMARY KEY (`id`),
UNIQUE (`order_no`),
UNIQUE (`normal_receipt_id`),
CHECK (quantity IN(1,2)),
CHECK (amount_cents=unit_price_cents*quantity),
CHECK (unit_price_cents>0),
CHECK ((status='CLOSED')=(closed_at IS NOT NULL AND close_reason IS NOT NULL)),
INDEX (`buyer_id`),
INDEX (`status`),
INDEX (`created_at`),
INDEX (`expires_at`)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS `inventory_ledger` (
`id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
`product_id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
`order_id` char(36) CHARACTER SET ascii COLLATE ascii_bin NULL,
`refund_id` char(36) CHARACTER SET ascii COLLATE ascii_bin NULL,
`actor_id` char(36) CHARACTER SET ascii COLLATE ascii_bin NULL,
`event_type` varchar(24) NOT NULL,
CHECK (`event_type` IN('RESERVE','CLOSE_RELEASE','REFUND_RELEASE','SHIP','ADJUST')),
`event_key` varchar(120) NOT NULL,
`delta_available` bigint NOT NULL,
`delta_reserved` bigint NOT NULL,
`delta_shipped` bigint NOT NULL,
`delta_adjustment` bigint NOT NULL,
`available_before` bigint NOT NULL,
`available_after` bigint NOT NULL,
`reserved_before` bigint NOT NULL,
`reserved_after` bigint NOT NULL,
`shipped_before` bigint NOT NULL,
`shipped_after` bigint NOT NULL,
`reason` varchar(500) NOT NULL,
`created_at` datetime(6) NOT NULL,
PRIMARY KEY (`id`),
UNIQUE (`event_key`),
INDEX (`order_id`),
INDEX (`created_at`)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS `payment_intents` (
`id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
`order_id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
`provider_request_id` varchar(80) NOT NULL,
`amount_cents` bigint NOT NULL,
CHECK (`amount_cents`>0),
`currency` char(3) NOT NULL,
CHECK (`currency`='CNY'),
`status` varchar(24) NOT NULL,
CHECK (`status` IN('READY','PENDING','SUCCEEDED','FAILED','UNKNOWN')),
`provider_txn_id` varchar(80) NULL,
`failure_code` varchar(64) NULL,
`last_queried_at` datetime(6) NULL,
`created_at` datetime(6) NOT NULL,
`updated_at` datetime(6) NOT NULL,
PRIMARY KEY (`id`),
UNIQUE (`provider_request_id`),
`active_order` char(36) GENERATED ALWAYS AS (CASE WHEN status<>'FAILED' THEN order_id ELSE NULL END) STORED,
UNIQUE (`active_order`),
INDEX (`order_id`),
INDEX (`status`),
INDEX (`created_at`)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS `receipts` (
`id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
`provider` varchar(24) NOT NULL,
`provider_txn_id` varchar(80) NOT NULL,
`external_order_ref` varchar(80) NOT NULL,
`order_id` char(36) CHARACTER SET ascii COLLATE ascii_bin NULL,
`payment_intent_id` char(36) CHARACTER SET ascii COLLATE ascii_bin NULL,
`amount_cents` bigint NOT NULL,
CHECK (`amount_cents`>0),
`currency` char(3) NOT NULL,
CHECK (`currency`='CNY'),
`classification` varchar(24) NOT NULL,
CHECK (`classification` IN('NORMAL','LATE','EXTRA','AMOUNT_MISMATCH','UNKNOWN_ORDER')),
`proof_type` varchar(16) NOT NULL,
CHECK (`proof_type` IN('SIGNED_NOTIFY','CHANNEL_QUERY')),
`verified_at` datetime(6) NOT NULL,
`provider_paid_at` datetime(6) NOT NULL,
`created_at` datetime(6) NOT NULL,
PRIMARY KEY (`id`),
UNIQUE (`provider`,`provider_txn_id`),
`normal_order` char(36) GENERATED ALWAYS AS (CASE WHEN classification='NORMAL' THEN order_id ELSE NULL END) STORED,
UNIQUE (`normal_order`),
INDEX (`order_id`),
INDEX (`created_at`)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS `channel_notifications` (
`id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
`kind` varchar(16) NOT NULL,
CHECK (`kind` IN('PAYMENT','REFUND')),
`provider` varchar(24) NOT NULL,
`provider_event_id` varchar(80) NULL,
`external_order_ref` varchar(80) NULL,
`provider_txn_id` varchar(80) NULL,
`provider_refund_id` varchar(80) NULL,
`claimed_amount_cents` bigint NULL,
`payload_hash` char(64) NOT NULL,
`payload_redacted` json NOT NULL,
`auth_valid` boolean NOT NULL,
`process_result` varchar(32) NOT NULL,
CHECK (`process_result` IN('ACCEPTED','DUPLICATE','INVALID_SIGNATURE','REPLAYED_SIGNATURE','AMOUNT_MISMATCH','UNKNOWN_ORDER','TXN_CONFLICT','INVALID_BODY','RESULT_CONFLICT','RETRYABLE')),
`reason_code` varchar(64) NOT NULL,
`receipt_id` char(36) CHARACTER SET ascii COLLATE ascii_bin NULL,
`refund_attempt_id` char(36) CHARACTER SET ascii COLLATE ascii_bin NULL,
`received_at` datetime(6) NOT NULL,
`processed_at` datetime(6) NULL,
PRIMARY KEY (`id`)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS `auth_nonces` (
`id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
`key_id` varchar(40) NOT NULL,
`nonce` varchar(64) NOT NULL,
`expires_at` datetime(6) NOT NULL,
`created_at` datetime(6) NOT NULL,
PRIMARY KEY (`id`),
UNIQUE (`key_id`,`nonce`),
INDEX (`created_at`),
INDEX (`expires_at`)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS `refund_applications` (
`id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
`order_id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
`buyer_id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
`reason` varchar(500) NOT NULL,
`status` varchar(16) NOT NULL,
CHECK (`status` IN('PENDING','APPROVED','REJECTED')),
`reviewer_id` char(36) CHARACTER SET ascii COLLATE ascii_bin NULL,
`review_reason` varchar(500) NULL,
`reviewed_at` datetime(6) NULL,
`created_at` datetime(6) NOT NULL,
PRIMARY KEY (`id`),
`pending_order` char(36) GENERATED ALWAYS AS (CASE WHEN status='PENDING' THEN order_id ELSE NULL END) STORED,
UNIQUE (`pending_order`),
INDEX (`order_id`),
INDEX (`buyer_id`),
INDEX (`status`),
INDEX (`created_at`)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS `refunds` (
`id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
`receipt_id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
`order_id` char(36) CHARACTER SET ascii COLLATE ascii_bin NULL,
`application_id` char(36) CHARACTER SET ascii COLLATE ascii_bin NULL,
`anomaly_id` char(36) CHARACTER SET ascii COLLATE ascii_bin NULL,
`kind` varchar(16) NOT NULL,
CHECK (`kind` IN('NORMAL','EXCEPTION')),
`amount_cents` bigint NOT NULL,
CHECK (`amount_cents`>0),
`status` varchar(16) NOT NULL,
CHECK (`status` IN('READY','PROCESSING','UNKNOWN','FAILED','SUCCEEDED')),
`current_attempt_id` char(36) CHARACTER SET ascii COLLATE ascii_bin NULL,
`created_by` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
`success_at` datetime(6) NULL,
`settled_at` datetime(6) NULL,
`created_at` datetime(6) NOT NULL,
`updated_at` datetime(6) NOT NULL,
PRIMARY KEY (`id`),
UNIQUE (`receipt_id`),
UNIQUE (`application_id`),
CHECK ((status='SUCCEEDED')=(settled_at IS NOT NULL)),
INDEX (`order_id`),
INDEX (`status`),
INDEX (`created_at`)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS `refund_attempts` (
`id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
`refund_id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
`attempt_no` int NOT NULL,
`provider_request_id` varchar(80) NOT NULL,
`provider_refund_id` varchar(80) NULL,
`status` varchar(16) NOT NULL,
CHECK (`status` IN('READY','PROCESSING','UNKNOWN','FAILED','SUCCEEDED')),
`failure_code` varchar(64) NULL,
`proof_redacted` json NOT NULL,
`sent_at` datetime(6) NULL,
`resolved_at` datetime(6) NULL,
`last_queried_at` datetime(6) NULL,
`created_at` datetime(6) NOT NULL,
PRIMARY KEY (`id`),
UNIQUE (`refund_id`,`attempt_no`),
UNIQUE (`provider_request_id`),
UNIQUE (`provider_refund_id`),
`active_refund` char(36) GENERATED ALWAYS AS (CASE WHEN status IN('READY','PROCESSING','UNKNOWN') THEN refund_id ELSE NULL END) STORED,
UNIQUE (`active_refund`),
INDEX (`status`),
INDEX (`created_at`)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS `shipments` (
`id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
`order_id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
`carrier` varchar(80) NOT NULL,
`tracking_no` varchar(80) NOT NULL,
`operator_id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
`shipped_at` datetime(6) NOT NULL,
PRIMARY KEY (`id`),
UNIQUE (`order_id`),
INDEX (`order_id`)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS `payment_anomalies` (
`id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
`type` varchar(32) NOT NULL,
CHECK (`type` IN('LATE_PAYMENT','INVALID_SIGNATURE','AMOUNT_MISMATCH','UNKNOWN_ORDER','TXN_CONFLICT','EXTRA_PAYMENT','REFUND_RESULT_CONFLICT','INVALID_BODY')),
`dedupe_key` varchar(160) NOT NULL,
`order_id` char(36) CHARACTER SET ascii COLLATE ascii_bin NULL,
`receipt_id` char(36) CHARACTER SET ascii COLLATE ascii_bin NULL,
`refund_id` char(36) CHARACTER SET ascii COLLATE ascii_bin NULL,
`first_notification_id` char(36) CHARACTER SET ascii COLLATE ascii_bin NULL,
`status` varchar(24) NOT NULL,
CHECK (`status` IN('OPEN','VERIFIED','REFUNDING','RESOLVED')),
`verification` varchar(24) NOT NULL,
CHECK (`verification` IN('UNVERIFIED','FUNDS_CONFIRMED','NO_FUNDS','CONFLICT')),
`summary` varchar(500) NOT NULL,
`resolved_reason` varchar(500) NULL,
`resolved_by` char(36) CHARACTER SET ascii COLLATE ascii_bin NULL,
`resolved_at` datetime(6) NULL,
`created_at` datetime(6) NOT NULL,
`updated_at` datetime(6) NOT NULL,
PRIMARY KEY (`id`),
UNIQUE (`dedupe_key`),
INDEX (`order_id`),
INDEX (`status`),
INDEX (`created_at`)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS `anomaly_actions` (
`id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
`anomaly_id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
`actor_id` char(36) CHARACTER SET ascii COLLATE ascii_bin NULL,
`action` varchar(24) NOT NULL,
CHECK (`action` IN('QUERY','VERIFY','REQUEST_REFUND','RETRY','RESOLVE','CONFLICT')),
`reason` varchar(500) NOT NULL,
`evidence_redacted` json NOT NULL,
`from_status` varchar(24) NOT NULL,
`to_status` varchar(24) NOT NULL,
`created_at` datetime(6) NOT NULL,
PRIMARY KEY (`id`),
INDEX (`created_at`)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS `idempotency_records` (
`id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
`actor_id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
`operation` varchar(80) NOT NULL,
`request_key` varchar(64) NOT NULL,
`request_hash` char(64) NOT NULL,
`resource_type` varchar(32) NOT NULL,
`resource_id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
`http_status` smallint NOT NULL,
`created_at` datetime(6) NOT NULL,
PRIMARY KEY (`id`),
UNIQUE (`actor_id`,`operation`,`request_key`),
INDEX (`created_at`)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS `outbox_jobs` (
`id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
`job_key` varchar(160) NOT NULL,
`kind` varchar(24) NOT NULL,
CHECK (`kind` IN('PAYMENT_SEND','REFUND_SEND','PAYMENT_QUERY','REFUND_QUERY')),
`aggregate_id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
`status` varchar(16) NOT NULL,
CHECK (`status` IN('READY','RUNNING','DONE','RETRY')),
`attempt_count` int NOT NULL,
`next_run_at` datetime(6) NOT NULL,
`lease_until` datetime(6) NULL,
`last_error_code` varchar(64) NULL,
`created_at` datetime(6) NOT NULL,
`updated_at` datetime(6) NOT NULL,
PRIMARY KEY (`id`),
UNIQUE (`job_key`),
INDEX (`status`),
INDEX (`created_at`),
INDEX (`next_run_at`)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS `audit_events` (
`id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
`actor_id` char(36) CHARACTER SET ascii COLLATE ascii_bin NULL,
`actor_kind` varchar(16) NOT NULL,
CHECK (`actor_kind` IN('USER','SYSTEM','CHANNEL')),
`entity_type` varchar(32) NOT NULL,
CHECK (`entity_type` IN('PRODUCT','ORDER','PAYMENT','REFUND','SHIPMENT','ANOMALY')),
`entity_id` char(36) CHARACTER SET ascii COLLATE ascii_bin NULL,
`action` varchar(64) NOT NULL,
`request_id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
`before_redacted` json NOT NULL,
`after_redacted` json NOT NULL,
`reason` varchar(500) NOT NULL,
`created_at` datetime(6) NOT NULL,
PRIMARY KEY (`id`),
INDEX (`created_at`)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS `demo_clock` (
`id` smallint NOT NULL,
`offset_seconds` bigint NOT NULL,
`version` bigint NOT NULL,
`updated_by` varchar(80) NOT NULL,
`updated_at` datetime(6) NOT NULL,
PRIMARY KEY (`id`)
) ENGINE=InnoDB;
ALTER TABLE `sessions` ADD FOREIGN KEY (`account_id`) REFERENCES `accounts` (`id`) ON DELETE RESTRICT;
ALTER TABLE `orders` ADD FOREIGN KEY (`buyer_id`) REFERENCES `accounts` (`id`) ON DELETE RESTRICT;
ALTER TABLE `orders` ADD FOREIGN KEY (`product_id`) REFERENCES `products` (`id`) ON DELETE RESTRICT;
ALTER TABLE `orders` ADD FOREIGN KEY (`normal_receipt_id`) REFERENCES `receipts` (`id`) ON DELETE RESTRICT;
ALTER TABLE `orders` ADD FOREIGN KEY (`active_application_id`) REFERENCES `refund_applications` (`id`) ON DELETE RESTRICT;
ALTER TABLE `inventory_ledger` ADD FOREIGN KEY (`product_id`) REFERENCES `products` (`id`) ON DELETE RESTRICT;
ALTER TABLE `inventory_ledger` ADD FOREIGN KEY (`order_id`) REFERENCES `orders` (`id`) ON DELETE RESTRICT;
ALTER TABLE `inventory_ledger` ADD FOREIGN KEY (`refund_id`) REFERENCES `refunds` (`id`) ON DELETE RESTRICT;
ALTER TABLE `inventory_ledger` ADD FOREIGN KEY (`actor_id`) REFERENCES `accounts` (`id`) ON DELETE RESTRICT;
ALTER TABLE `payment_intents` ADD FOREIGN KEY (`order_id`) REFERENCES `orders` (`id`) ON DELETE RESTRICT;
ALTER TABLE `receipts` ADD FOREIGN KEY (`order_id`) REFERENCES `orders` (`id`) ON DELETE RESTRICT;
ALTER TABLE `receipts` ADD FOREIGN KEY (`payment_intent_id`) REFERENCES `payment_intents` (`id`) ON DELETE RESTRICT;
ALTER TABLE `channel_notifications` ADD FOREIGN KEY (`receipt_id`) REFERENCES `receipts` (`id`) ON DELETE RESTRICT;
ALTER TABLE `channel_notifications` ADD FOREIGN KEY (`refund_attempt_id`) REFERENCES `refund_attempts` (`id`) ON DELETE RESTRICT;
ALTER TABLE `refund_applications` ADD FOREIGN KEY (`order_id`) REFERENCES `orders` (`id`) ON DELETE RESTRICT;
ALTER TABLE `refund_applications` ADD FOREIGN KEY (`buyer_id`) REFERENCES `accounts` (`id`) ON DELETE RESTRICT;
ALTER TABLE `refund_applications` ADD FOREIGN KEY (`reviewer_id`) REFERENCES `accounts` (`id`) ON DELETE RESTRICT;
ALTER TABLE `refunds` ADD FOREIGN KEY (`receipt_id`) REFERENCES `receipts` (`id`) ON DELETE RESTRICT;
ALTER TABLE `refunds` ADD FOREIGN KEY (`order_id`) REFERENCES `orders` (`id`) ON DELETE RESTRICT;
ALTER TABLE `refunds` ADD FOREIGN KEY (`application_id`) REFERENCES `refund_applications` (`id`) ON DELETE RESTRICT;
ALTER TABLE `refunds` ADD FOREIGN KEY (`anomaly_id`) REFERENCES `payment_anomalies` (`id`) ON DELETE RESTRICT;
ALTER TABLE `refunds` ADD FOREIGN KEY (`current_attempt_id`) REFERENCES `refund_attempts` (`id`) ON DELETE RESTRICT;
ALTER TABLE `refunds` ADD FOREIGN KEY (`created_by`) REFERENCES `accounts` (`id`) ON DELETE RESTRICT;
ALTER TABLE `refund_attempts` ADD FOREIGN KEY (`refund_id`) REFERENCES `refunds` (`id`) ON DELETE RESTRICT;
ALTER TABLE `shipments` ADD FOREIGN KEY (`order_id`) REFERENCES `orders` (`id`) ON DELETE RESTRICT;
ALTER TABLE `shipments` ADD FOREIGN KEY (`operator_id`) REFERENCES `accounts` (`id`) ON DELETE RESTRICT;
ALTER TABLE `payment_anomalies` ADD FOREIGN KEY (`order_id`) REFERENCES `orders` (`id`) ON DELETE RESTRICT;
ALTER TABLE `payment_anomalies` ADD FOREIGN KEY (`receipt_id`) REFERENCES `receipts` (`id`) ON DELETE RESTRICT;
ALTER TABLE `payment_anomalies` ADD FOREIGN KEY (`refund_id`) REFERENCES `refunds` (`id`) ON DELETE RESTRICT;
ALTER TABLE `payment_anomalies` ADD FOREIGN KEY (`first_notification_id`) REFERENCES `channel_notifications` (`id`) ON DELETE RESTRICT;
ALTER TABLE `payment_anomalies` ADD FOREIGN KEY (`resolved_by`) REFERENCES `accounts` (`id`) ON DELETE RESTRICT;
ALTER TABLE `anomaly_actions` ADD FOREIGN KEY (`anomaly_id`) REFERENCES `payment_anomalies` (`id`) ON DELETE RESTRICT;
ALTER TABLE `anomaly_actions` ADD FOREIGN KEY (`actor_id`) REFERENCES `accounts` (`id`) ON DELETE RESTRICT;
ALTER TABLE `idempotency_records` ADD FOREIGN KEY (`actor_id`) REFERENCES `accounts` (`id`) ON DELETE RESTRICT;
ALTER TABLE `audit_events` ADD FOREIGN KEY (`actor_id`) REFERENCES `accounts` (`id`) ON DELETE RESTRICT;
