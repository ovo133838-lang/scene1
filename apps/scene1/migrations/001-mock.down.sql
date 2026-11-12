-- DESTRUCTIVE: isolated test DB only; never automatically invoked
SET FOREIGN_KEY_CHECKS=0;
DROP TABLE IF EXISTS `auth_nonces`;
DROP TABLE IF EXISTS `simulation_rules`;
DROP TABLE IF EXISTS `notification_jobs`;
DROP TABLE IF EXISTS `channel_refunds`;
DROP TABLE IF EXISTS `channel_payments`;
SET FOREIGN_KEY_CHECKS=1;
