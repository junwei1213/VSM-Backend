#!/bin/bash
# 通知系统测试脚本

BASE_URL="http://localhost:8000"

echo "=== VSM 通知系统 API 测试 ==="
echo ""

# 1. 获取公告
echo "1. 获取公告列表:"
curl -s "${BASE_URL}/api/notices" | python3 -m json.tool
echo ""

# 2. 获取公告 (只获取 banner)
echo "2. 获取 Banner 公告:"
curl -s "${BASE_URL}/api/notices?type=banner&limit=1" | python3 -m json.tool
echo ""

# 3. 测试未授权访问 (应该返回 401)
echo "3. 测试未授权访问通知列表:"
curl -s -w "\nHTTP Status: %{http_code}\n" "${BASE_URL}/api/notifications"
echo ""

echo "=== 测试完成 ==="
echo ""
echo "注意: 用户通知API需要有效的JWT Token"
echo "Admin 通知API需要管理员权限"
