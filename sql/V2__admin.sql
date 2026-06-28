-- V2: 管理系统相关表变更
USE smart_interview;

-- 1. users 表新增字段
ALTER TABLE users ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'USER' COMMENT '角色: USER/ADMIN';
ALTER TABLE users ADD COLUMN enabled TINYINT(1) NOT NULL DEFAULT 1 COMMENT '账号启用';
ALTER TABLE users ADD COLUMN phone VARCHAR(20) COMMENT '手机号';
ALTER TABLE users ADD COLUMN avatar_url VARCHAR(500) COMMENT '头像URL';

-- 2. 系统配置表
CREATE TABLE IF NOT EXISTS system_configs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    config_key VARCHAR(100) NOT NULL UNIQUE,
    config_value TEXT,
    description VARCHAR(255),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3. 插入默认系统配置
INSERT INTO system_configs (config_key, config_value, description) VALUES
('site_name', 'SmartInterview', '系统名称'),
('max_questions_per_interview', '12', '每次面试最大题目数'),
('default_difficulty', 'medium', '默认难度');

-- 4. 管理员账号由应用启动时 DataInitializer 自动创建 (admin / admin123)
