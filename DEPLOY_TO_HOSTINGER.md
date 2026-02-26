# Hostinger 部署指南

## 架构说明

| 环境 | API 地址 | 说明 |
|------|---------|------|
| **本地开发** | `http://localhost:8000` | 本地开发环境 |
| **Cloudflare Tunnel** | `https://vsm-api.justintan.my` | 本地通过 Tunnel 暴露 |
| **Hostinger 生产** | `https://goveggiemalaysia.cloud/api` | 生产环境 |

⚠️ **重要**: Hostinger 与本地是两套独立环境，需要分别部署！

---

## 方案 1: Git 部署（推荐）

### 1. 检查 GitHub 仓库

```bash
cd /Users/justin/Developer/VSM-Backend
git status
git log --oneline -5
```

### 2. Push 最新代码到 GitHub

```bash
git add .
git commit -m "feat: add notifications, enhanced search API"
git push origin main
```

### 3. Hostinger 服务器拉取更新

SSH 到 Hostinger 服务器:

```bash
ssh username@goveggiemalaysia.cloud
# 或
ssh hostinger_server_ip
```

在服务器上:

```bash
cd ~/VSM-Backend  # 或项目目录
git pull origin main

# 安装依赖
pip3 install -r requirements.txt

# 重启服务
sudo systemctl restart vsm-api
# 或
pkill -f uvicorn
nohup python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 > api.log 2>&1 &
```

---

## 方案 2: 数据库同步

### 本地导出结构变更

```bash
# 导出新增表结构
mysqldump -u root --no-data goveggie_v4 \
  user_notifications \
  user_devices \
  new_restaurant_notifications \
  > hostinger_migration.sql

# 导出 notices 表（如果有数据）
mysqldump -u root goveggie_v4 notices >> hostinger_migration.sql
```

### Hostinger 数据库导入

```bash
# 通过 Adminer 或 MySQL 客户端导入
mysql -u hostinger_user -p hostinger_db < hostinger_migration.sql
```

---

## 方案 3: 使用 Cloudflare Tunnel（临时方案）

如果不想部署到 Hostinger，可以修改 VSM App 指向本地 Tunnel:

### 修改 VSM App API 地址

```dart
// lib/services/api_service.dart
// 临时切换到本地 Tunnel
static const String baseUrl = 'https://vsm-api.justintan.my';
```

然后:
1. 确保本地 API 运行 (`localhost:8000`)
2. 启动 Cloudflare Tunnel
3. VSM App 即可访问最新功能

---

## 快速检查清单

### 部署前检查

- [ ] 本地代码已测试通过
- [ ] `main.py` 语法检查通过 (`python3 -c "import main"`)
- [ ] 数据库迁移脚本已准备
- [ ] Git commit 已提交

### 部署后验证

```bash
# 1. 检查 API 运行
curl https://goveggiemalaysia.cloud/api/restaurants?limit=1

# 2. 检查通知功能
curl https://goveggiemalaysia.cloud/api/notices

# 3. 检查搜索筛选
curl https://goveggiemalaysia.cloud/api/search/filters
```

---

## 数据库迁移 SQL

```sql
-- 用户通知表
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
  INDEX idx_is_read (is_read)
);

-- 用户设备表
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
);

-- 新餐厅通知记录表
CREATE TABLE IF NOT EXISTS new_restaurant_notifications (
  id INT PRIMARY KEY AUTO_INCREMENT,
  restaurant_id INT NOT NULL,
  notification_sent TINYINT(1) DEFAULT 0,
  sent_at TIMESTAMP NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY unique_restaurant (restaurant_id)
);

-- 确保 notices 表存在
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
  deleted_at TIMESTAMP NULL
);
```

---

## Hostinger 配置参考

### 服务器路径（假设）

```
/home/username/VSM-Backend/     # API 代码
/var/www/html/                  # Web 根目录
/etc/systemd/system/vsm-api.service  # 系统服务
```

### Nginx 配置（Hostinger）

```nginx
server {
    listen 80;
    server_name goveggiemalaysia.cloud;
    
    location /api {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## 问题排查

### API 无法启动

```bash
# 检查日志
tail -f ~/VSM-Backend/api.log

# 检查端口占用
sudo lsof -i :8000

# 检查依赖
pip3 list | grep -E "fastapi|uvicorn|mysql"
```

### 数据库连接失败

```bash
# 检查 MySQL 运行状态
sudo systemctl status mysql

# 检查数据库用户权限
mysql -u root -p -e "SHOW GRANTS FOR 'vsm_user'@'localhost'"
```
