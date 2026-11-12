CREATE TABLE IF NOT EXISTS `channel_payments` (
`id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
`merchant_ref` varchar(40) NOT NULL,
`request_id` varchar(80) NOT NULL,
`order_ref` varchar(80) NOT NULL,
`txn_id` varchar(80) NOT NULL,
`amount_cents` bigint NOT NULL,
CHECK (`amount_cents`>0),
`currency` char(3) NOT NULL,
CHECK (`currency`='CNY'),
`status` varchar(16) NOT NULL,
CHECK (`status` IN('PENDING','SUCCEEDED','FAILED')),
`paid_at` datetime(6) NULL,
`created_at` datetime(6) NOT NULL,
`updated_at` datetime(6) NOT NULL,
PRIMARY KEY (`id`),
UNIQUE (`merchant_ref`,`request_id`),
UNIQUE (`txn_id`),
INDEX (`status`),
INDEX (`created_at`)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS `channel_refunds` (
`id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
`merchant_ref` varchar(40) NOT NULL,
`request_id` varchar(80) NOT NULL,
`txn_id` varchar(80) NOT NULL,
`refund_id` varchar(80) NOT NULL,
`amount_cents` bigint NOT NULL,
CHECK (`amount_cents`>0),
`status` varchar(16) NOT NULL,
CHECK (`status` IN('PENDING','SUCCEEDED','FAILED')),
`failure_code` varchar(64) NULL,
`refunded_at` datetime(6) NULL,
`created_at` datetime(6) NOT NULL,
`updated_at` datetime(6) NOT NULL,
PRIMARY KEY (`id`),
UNIQUE (`merchant_ref`,`request_id`),
UNIQUE (`refund_id`),
INDEX (`status`),
INDEX (`created_at`)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS `notification_jobs` (
`id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
`kind` varchar(16) NOT NULL,
CHECK (`kind` IN('PAYMENT','REFUND')),
`resource_ref` varchar(80) NOT NULL,
`event_id` varchar(80) NOT NULL,
`deliver_after` datetime(6) NOT NULL,
`remaining_deliveries` int NOT NULL,
`status` varchar(16) NOT NULL,
CHECK (`status` IN('READY','RUNNING','DONE','RETRY')),
`lease_until` datetime(6) NULL,
`last_http_status` smallint NULL,
`created_at` datetime(6) NOT NULL,
PRIMARY KEY (`id`),
UNIQUE (`event_id`),
INDEX (`status`),
INDEX (`created_at`),
INDEX (`deliver_after`)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS `simulation_rules` (
`id` char(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
`target_order_ref` varchar(80) NOT NULL,
`target_request_id` varchar(80) NULL,
`attempt_no` int NULL,
`operation` varchar(16) NOT NULL,
CHECK (`operation` IN('PAYMENT','REFUND','NOTIFY')),
`mode` varchar(32) NOT NULL,
CHECK (`mode` IN('SUCCESS','EXPLICIT_FAIL','TIMEOUT_AFTER_SUCCESS','PENDING','DELAY_NOTIFY','DUPLICATE_NOTIFY')),
`delay_ms` int NOT NULL,
`repeat_count` int NOT NULL,
`remaining_uses` int NOT NULL,
`created_at` datetime(6) NOT NULL,
PRIMARY KEY (`id`),
INDEX (`created_at`)
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
ALTER TABLE `channel_refunds` ADD FOREIGN KEY (`txn_id`) REFERENCES `channel_payments` (`txn_id`) ON DELETE RESTRICT;
CREATE TABLE IF NOT EXISTS runtime_lock (id smallint PRIMARY KEY); INSERT IGNORE INTO runtime_lock VALUES(1);