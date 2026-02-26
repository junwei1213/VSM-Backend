-- ============================================
-- VSM Backend Migration for Hostinger
-- Date: 2026-02-13
-- From: goveggie_v4 (local) -> Hostinger Production
-- ============================================

-- 1. 用户通知表
CREATE TABLE IF NOT EXISTS user_notifications (
  id INT PRIMARY KEY AUTO_INCREMENT,
  user_id INT NOT NULL,
  type ENUM('new_restaurant', 'announcement', 'promotion', 'update') NOT NULL DEFAULT 'announcement',
  title VARCHAR(255) NOT NULL,
  content TEXT,
  data JSON,
  is_read TINYINT(1) DEFAULT 0,
  read_at TIMESTAMP NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_user_id (user_id),
  INDEX idx_is_read (is_read),
  INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. 用户设备表
CREATE TABLE IF NOT EXISTS user_devices (
  id INT PRIMARY KEY AUTO_INCREMENT,
  user_id INT,
  device_token VARCHAR(255) NOT NULL,
  device_type ENUM('ios', 'android', 'huawei') NOT NULL,
  app_version VARCHAR(20),
  is_active TINYINT(1) DEFAULT 1,
  last_used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY unique_device_token (device_token),
  INDEX idx_user_id (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3. 新餐厅通知记录表
CREATE TABLE IF NOT EXISTS new_restaurant_notifications (
  id INT PRIMARY KEY AUTO_INCREMENT,
  restaurant_id INT NOT NULL,
  notification_sent TINYINT(1) DEFAULT 0,
  sent_at TIMESTAMP NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY unique_restaurant (restaurant_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 4. 确保 notices 表结构正确
CREATE TABLE IF NOT EXISTS notices (
  id INT PRIMARY KEY AUTO_INCREMENT,
  type ENUM('banner','popup') NOT NULL DEFAULT 'banner',
  content TEXT,
  info TEXT,
  image_url VARCHAR(500),
  link_name VARCHAR(100),
  links JSON,
  is_active TINYINT(1) DEFAULT 1,
  priority INT DEFAULT 0,
  created_by INT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  deleted_at TIMESTAMP NULL,
  INDEX idx_is_active (is_active),
  INDEX idx_priority (priority)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 5. 插入默认公告数据
INSERT INTO notices (type, content, info, is_active, priority) VALUES
('banner', '🎉 GoVeggie Q1 Beta 上线啦！欢迎试用并提供宝贵意见', 'v1.0.0 Beta', 1, 1)
ON DUPLICATE KEY UPDATE content=VALUES(content);

-- 6. 确保 restaurants 表有需要的字段
-- 检查并添加 recommended 字段（如果不存在）
SET @exist := (SELECT COUNT(*) FROM information_schema.columns 
  WHERE table_name = 'restaurants' AND column_name = 'recommended' AND table_schema = DATABASE());
SET @sql := IF(@exist = 0, 'ALTER TABLE restaurants ADD COLUMN recommended TINYINT(1) DEFAULT 0', 'SELECT "Column already exists"');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 检查并添加 price_level 字段（如果不存在）
SET @exist := (SELECT COUNT(*) FROM information_schema.columns 
  WHERE table_name = 'restaurants' AND column_name = 'price_level' AND table_schema = DATABASE());
SET @sql := IF(@exist = 0, 'ALTER TABLE restaurants ADD COLUMN price_level INT DEFAULT 1', 'SELECT "Column already exists"');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 检查并添加 time_slots 字段（如果不存在）
SET @exist := (SELECT COUNT(*) FROM information_schema.columns 
  WHERE table_name = 'restaurants' AND column_name = 'time_slots' AND table_schema = DATABASE());
SET @sql := IF(@exist = 0, 'ALTER TABLE restaurants ADD COLUMN time_slots JSON', 'SELECT "Column already exists"');
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SELECT 'Migration completed successfully!' as status;
