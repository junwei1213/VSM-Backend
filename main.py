"""
GoVeggie API v2.0 - Q1 Version
Database: goveggie_v4
Run: uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

from fastapi import FastAPI, Query, Header, HTTPException, Depends, Request, UploadFile, File
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import mysql.connector
import json
import os
import jwt
from datetime import datetime, timedelta, timezone
from typing import Optional, List
from pydantic import BaseModel

app = FastAPI(title="GoVeggie API v2.0", version="2.0")

# Security
SECRET_KEY = "vsm-super-secret-key-for-jwt-2026"
ALGORITHM = "HS256"
STATIC_API_KEY = "vsm-q1-beta-key-2026"
security = HTTPBearer(auto_error=False)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=365)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def verify_token(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    if not credentials or not credentials.credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

async def verify_token_or_key(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    api_key: Optional[str] = Query(None),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
):
    if request.method == "GET":
        return {"sub": "beta_guest", "role": "guest"}
    
    key = x_api_key or api_key
    if key == STATIC_API_KEY:
        return {"sub": "static_client", "role": "guest"}
    if credentials and credentials.credentials:
        try:
            return jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        except: pass
    raise HTTPException(status_code=403, detail="Invalid credentials")

def get_current_user(payload: dict = Depends(verify_token)):
    return payload

def require_admin(user: dict = Depends(verify_token)):
    if user.get('role') not in ['admin', 'super_admin']:
        raise HTTPException(status_code=403, detail="Admin only")
    return user

# Photo storage path
PHOTO_DIR = "/Users/justin/python/GoVeggie/data/images"
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        database="goveggie_v4",
        charset="utf8mb4",
    )

def parse_json_field(val):
    if val is None: return None
    if isinstance(val, str):
        try: return json.loads(val)
        except: return val
    return val

def row_to_dict(row):
    from decimal import Decimal
    json_fields = ['phones', 'time_slots', 'rest_days', 'diet_tags', 'food_tags', 'facility_tags', 'photos', 'business_hours', 'device_tokens', 'preferences']
    for f in json_fields:
        if f in row: row[f] = parse_json_field(row[f])
    for key, value in row.items():
        if isinstance(value, Decimal): row[key] = float(value)
    return row

# ============================================================
# Auth Endpoints
# ============================================================

class SocialLoginRequest(BaseModel):
    provider: str
    provider_id: str
    email: Optional[str] = None
    name: Optional[str] = None
    avatar_url: Optional[str] = None

@app.post("/api/auth/social-login")
def social_login(req: SocialLoginRequest):
    if req.provider not in ("google", "apple", "facebook", "huawei"):
        raise HTTPException(status_code=400, detail="Unsupported provider")
    db = get_db(); cursor = db.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM users WHERE auth_provider=%s AND auth_provider_id=%s", (req.provider, req.provider_id))
        user = cursor.fetchone()
        if not user and req.email:
            cursor.execute("SELECT * FROM users WHERE email=%s", (req.email,))
            user = cursor.fetchone()
            if user:
                cursor.execute("UPDATE users SET auth_provider=%s, auth_provider_id=%s, last_login_at=NOW() WHERE id=%s", 
                             (req.provider, req.provider_id, user['id']))
                db.commit()
        if not user:
            admin_emails = ["admin@vsm.org.my", "justinjunwei2002@gmail.com", "iuqe12@gmail.com"]
            role = "admin" if req.email in admin_emails else "user"
            cursor.execute(
                "INSERT INTO users (email, name, avatar_url, auth_provider, auth_provider_id, role, is_active, last_login_at) VALUES (%s,%s,%s,%s,%s,%s,1,NOW())",
                (req.email, req.name, req.avatar_url, req.provider, req.provider_id, role))
            db.commit(); uid = cursor.lastrowid
            role_out = role
        else:
            uid = user['id']; role_out = user['role']
            cursor.execute("UPDATE users SET last_login_at=NOW() WHERE id=%s", (uid,))
            db.commit()
        token = create_access_token({"sub": str(uid), "uid": uid, "role": role_out})
        need_phone = True
        if user and user.get('phone'): need_phone = False
        return {"token": token, "uid": uid, "role": role_out, "need_phone": need_phone}
    finally: cursor.close(); db.close()

class BindPhoneRequest(BaseModel):
    phone: str

@app.post("/api/auth/bind-phone")
def bind_phone(req: BindPhoneRequest, user: dict = Depends(verify_token)):
    db = get_db(); cursor = db.cursor()
    try:
        cursor.execute("SELECT id FROM users WHERE phone=%s AND id!=%s", (req.phone, user['uid']))
        if cursor.fetchone():
            raise HTTPException(status_code=409, detail="Phone already linked")
        cursor.execute("UPDATE users SET phone=%s WHERE id=%s", (req.phone, user['uid']))
        db.commit(); return {"ok": True}
    finally: cursor.close(); db.close()

@app.get("/api/auth/me")
def get_me(user: dict = Depends(verify_token)):
    db = get_db(); cursor = db.cursor(dictionary=True)
    try:
        cursor.execute("SELECT id, phone, email, name, avatar_url, role, preferences, created_at FROM users WHERE id=%s", (user['uid'],))
        u = cursor.fetchone()
        if not u: raise HTTPException(status_code=404, detail="User not found")
        return row_to_dict(u)
    finally: cursor.close(); db.close()

# ============================================================
# Restaurants Endpoints
# ============================================================

@app.get("/api/restaurants", dependencies=[Depends(verify_token_or_key)])
def list_restaurants(
    # 基础筛选
    state_id: Optional[int] = None,
    area: Optional[str] = None,
    search: Optional[str] = None,
    
    # 价格筛选
    price_level: Optional[int] = None,
    price_min: Optional[int] = None,
    price_max: Optional[int] = None,
    
    # 特色筛选
    recommended: Optional[bool] = None,
    
    # 时间筛选
    time_slot: Optional[str] = None,  # morning, afternoon, evening
    is_open_now: Optional[bool] = None,
    
    # 地理位置排序
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    radius: Optional[int] = 50000,  # 默认50km
    
    # 排序
    sort_by: Optional[str] = Query(None, description="排序方式: distance, newest, recommended (Q1: 无rating/saves)"),
    
    # 分页
    page: int = 1,
    limit: int = 50
):
    """
    增强版餐厅搜索 API
    
    搜索字段: 名称(中英文)、地址、推荐菜、描述、电话
    
    筛选条件:
    - state_id: 州属ID
    - area: 地区名称(如"Kuala Lumpur")
    - price_level: 价格等级(1-3)
    - price_min/price_max: 价格范围
    - recommended: 是否推荐餐厅
    - time_slot: 营业时段(morning/afternoon/evening)
    - is_open_now: 是否正在营业
    
    排序 (Q1版本无rating/saves):
    - distance: 距离最近(需lat/lng)
    - newest: 最新加入
    - recommended: 推荐优先
    """
    db = get_db(); cursor = db.cursor(dictionary=True)
    where = ["1=1"]; params = []
    joins = []

    # 1. 州属筛选 (通过 state_id 查找 state 名称)
    if state_id:
        cursor.execute("SELECT name FROM states WHERE id = %s", (state_id,))
        state_row = cursor.fetchone()
        if state_row:
            where.append("r.state = %s")
            params.append(state_row['name'])
    
    # 2. 地区筛选 (直接匹配 area 名称)
    if area:
        where.append("r.area = %s")
        params.append(area)
    
    # 3. 增强搜索 (多字段模糊搜索)
    if search:
        q = f"%{search}%"
        # 支持中英文名称、地址、推荐菜、描述、电话
        search_conditions = [
            "r.name_zh LIKE %s", 
            "r.name_en LIKE %s",
            "r.address LIKE %s",
            "r.recommended_dishes LIKE %s",
            "r.description LIKE %s",
            "JSON_SEARCH(r.phones, 'one', %s) IS NOT NULL"  # 搜索电话号码
        ]
        where.append(f"({' OR '.join(search_conditions)})")
        params.extend([q, q, q, q, q, search])  # phones 用原始搜索词
    
    # 4. 价格筛选
    if price_level is not None:
        where.append("r.price_level = %s")
        params.append(price_level)
    if price_min is not None:
        where.append("r.price_level >= %s")
        params.append(price_min)
    if price_max is not None:
        where.append("r.price_level <= %s")
        params.append(price_max)
    
    # 5. 推荐餐厅筛选
    if recommended is not None:
        if recommended:
            where.append("r.recommended = 1")
        else:
            where.append("(r.recommended = 0 OR r.recommended IS NULL)")
    
    # 6. 营业时段筛选 (time_slots JSON)
    if time_slot:
        valid_slots = ['morning', 'afternoon', 'evening', 'night']
        if time_slot in valid_slots:
            where.append("JSON_CONTAINS(r.time_slots, %s)")
            params.append(json.dumps(time_slot))
    
    # 8. 正在营业筛选
    if is_open_now:
        # 获取当前时间
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        current_day = now.strftime("%A")  # Monday, Tuesday...
        # 简化版：检查 rest_days 不包含今天
        where.append("(r.rest_days IS NULL OR r.rest_days NOT LIKE %s)")
        params.append(f"%{current_day}%")
    
    # 9. 距离筛选和排序
    dist_select = ""
    dist_where = ""
    order_by = "r.id DESC"  # 默认排序
    
    if lat is not None and lng is not None:
        try:
            f_lat = float(lat); f_lng = float(lng)
            if abs(f_lat) > 0.1:
                # 计算距离
                dist_select = f", (6371000 * acos(least(1.0, cos(radians({f_lat})) * cos(radians(r.location_lat)) * cos(radians(r.location_lng) - radians({f_lng})) + sin(radians({f_lat})) * sin(radians(r.location_lat))))) AS distance_m"
                # 限制半径
                dist_where = f" AND (6371000 * acos(least(1.0, cos(radians({f_lat})) * cos(radians(r.location_lat)) * cos(radians(r.location_lng) - radians({f_lng})) + sin(radians({f_lat})) * sin(radians(r.location_lat))))) <= {radius}"
                
                # 根据 sort_by 参数决定排序
                if sort_by == "distance":
                    order_by = "distance_m ASC"
        except:
            pass
    
    # 排序处理 (Q1版本: 无rating/saves排序)
    if sort_by == "newest":
        order_by = "r.created_at DESC"
    elif sort_by == "recommended":
        order_by = "r.recommended DESC, r.id DESC"  # 推荐优先，其次按ID
    elif sort_by == "distance" and not (lat and lng):
        # 如果没有提供坐标，忽略距离排序
        order_by = "r.id DESC"
    
    where_str = " AND ".join(where)
    offset = (page - 1) * limit
    
    # 构建最终 SQL (WHERE 条件参数 + 分页参数)
    sql_params = params.copy()
    sql = f"""SELECT r.*, 
                     s.name as state_name, s.name_zh as state_name_zh, 
                     a.area as area_name, a.area_zh as area_name_zh
                     {dist_select}
              FROM restaurants r 
              LEFT JOIN states s ON CAST(s.name AS CHAR CHARACTER SET utf8mb4) = CAST(r.state AS CHAR CHARACTER SET utf8mb4)
              LEFT JOIN areas a ON CAST(a.area AS CHAR CHARACTER SET utf8mb4) = CAST(r.area AS CHAR CHARACTER SET utf8mb4)
              WHERE {where_str} {dist_where}
              ORDER BY {order_by}
              LIMIT %s OFFSET %s"""
    sql_params.extend([limit, offset])
    
    # 执行查询
    cursor.execute(sql, sql_params)
    rows = [row_to_dict(r) for r in cursor.fetchall()]
    
    # 获取总数 (使用原始 params，不包含分页参数)
    count_sql = f"SELECT COUNT(*) as total FROM restaurants r WHERE {where_str}"
    cursor.execute(count_sql, params)
    total = cursor.fetchone()['total']
    
    cursor.close(); db.close()
    
    return {
        "total": total,
        "page": page,
        "limit": limit,
        "filters_applied": {
            "state_id": state_id,
            "area": area,
            "search": search,
            "price_level": price_level,
            "price_range": {"min": price_min, "max": price_max} if (price_min or price_max) else None,
            "recommended": recommended,
            "time_slot": time_slot,
            "is_open_now": is_open_now,
            "sort_by": sort_by,
            "location": {"lat": lat, "lng": lng, "radius": radius} if lat and lng else None
        },
        "data": rows
    }

@app.get("/api/restaurants/{restaurant_id}")
def get_restaurant(restaurant_id: int):
    db = get_db(); cursor = db.cursor(dictionary=True)
    cursor.execute("""SELECT r.*, s.name as state_name, s.name_zh as state_name_zh, 
                        a.area as area_name, a.area_zh as area_name_zh 
                      FROM restaurants r 
                      LEFT JOIN states s ON CAST(s.name AS CHAR CHARACTER SET utf8mb4) = CAST(r.state AS CHAR CHARACTER SET utf8mb4)
                      LEFT JOIN areas a ON CAST(a.area AS CHAR CHARACTER SET utf8mb4) = CAST(r.area AS CHAR CHARACTER SET utf8mb4)
                      WHERE r.id = %s""", (restaurant_id,))
    row = cursor.fetchone(); cursor.close(); db.close()
    if not row: raise HTTPException(status_code=404, detail="Not found")
    return row_to_dict(row)


@app.get("/api/search/suggestions")
def search_suggestions(
    q: str = Query(..., min_length=1, description="搜索关键词"),
    limit: int = 10
):
    """
    搜索建议 API - 返回餐厅名称、地区、推荐菜等建议
    用于搜索框自动补全
    """
    db = get_db(); cursor = db.cursor(dictionary=True)
    suggestions = []
    
    try:
        search_q = f"%{q}%"
        
        # 1. 搜索餐厅名称 (中英文)
        cursor.execute("""
            SELECT DISTINCT 
                CASE 
                    WHEN name_zh LIKE %s AND name_zh IS NOT NULL THEN name_zh
                    ELSE name_en 
                END as name,
                state, area
            FROM restaurants 
            WHERE (name_zh LIKE %s OR name_en LIKE %s)
            AND (name_zh IS NOT NULL OR name_en IS NOT NULL)
            LIMIT %s
        """, (search_q, search_q, search_q, limit))
        
        for row in cursor.fetchall():
            if row['name']:
                suggestions.append({
                    "type": "restaurant",
                    "text": row['name'],
                    "location": f"{row['state']}, {row['area']}" if row['area'] else row['state']
                })
        
        # 2. 搜索地区
        if len(suggestions) < limit:
            cursor.execute("""
                SELECT DISTINCT area, state 
                FROM areas 
                WHERE area LIKE %s OR area_zh LIKE %s
                LIMIT %s
            """, (search_q, search_q, limit - len(suggestions)))
            
            for row in cursor.fetchall():
                suggestions.append({
                    "type": "area",
                    "text": row['area'],
                    "state": row['state']
                })
        
        # 3. 搜索推荐菜
        if len(suggestions) < limit:
            cursor.execute("""
                SELECT DISTINCT recommended_dishes
                FROM restaurants 
                WHERE recommended_dishes LIKE %s
                LIMIT %s
            """, (search_q, limit - len(suggestions)))
            
            for row in cursor.fetchall():
                if row['recommended_dishes']:
                    # 简单拆分推荐菜
                    dishes = row['recommended_dishes'].replace('，', ',').split(',')
                    for dish in dishes[:3]:  # 最多取3个
                        dish = dish.strip()
                        if q.lower() in dish.lower() and len(suggestions) < limit:
                            suggestions.append({
                                "type": "dish",
                                "text": dish
                            })
        
        # 4. 热门搜索关键词 (基于搜索历史或预设)
        hot_keywords = ["素食", "vegan", "火锅", "早餐", "经济饭", "咖啡", "Kuala Lumpur", "Penang"]
        matching_hot = [k for k in hot_keywords if q.lower() in k.lower()]
        for kw in matching_hot[:3]:
            if len(suggestions) < limit:
                suggestions.append({
                    "type": "hot",
                    "text": kw
                })
        
    finally:
        cursor.close(); db.close()
    
    return {
        "query": q,
        "suggestions": suggestions[:limit]
    }


@app.get("/api/search/filters")
def get_search_filters():
    """
    获取所有可用的搜索筛选选项
    用于前端筛选器展示
    """
    db = get_db(); cursor = db.cursor(dictionary=True)
    
    try:
        # 价格等级 (Q1版本: 1-3级)
        price_levels = [
            {"value": 1, "label": "$", "label_en": "Budget", "label_zh": "经济"},
            {"value": 2, "label": "$$", "label_en": "Moderate", "label_zh": "中等"},
            {"value": 3, "label": "$$$", "label_en": "Expensive", "label_zh": "较贵"}
        ]
        
        # 营业时段
        time_slots = [
            {"value": "morning", "label": "早餐", "label_en": "Morning", "hours": "6:00 - 11:00"},
            {"value": "afternoon", "label": "午餐", "label_en": "Afternoon", "hours": "11:00 - 15:00"},
            {"value": "evening", "label": "晚餐", "label_en": "Evening", "hours": "18:00 - 22:00"},
            {"value": "night", "label": "宵夜", "label_en": "Night", "hours": "22:00 - 2:00"}
        ]
        
        # 排序选项 (Q1版本: 无rating/saves，favorites表为空)
        sort_options = [
            {"value": "recommended", "label": "推荐优先", "label_en": "Recommended"},
            {"value": "distance", "label": "距离最近", "label_en": "Nearest"},
            {"value": "newest", "label": "最新加入", "label_en": "Newest"}
        ]
        
        # 特色筛选
        features = [
            {"value": "recommended", "label": "推荐餐厅", "label_en": "Recommended"},
            {"value": "is_open_now", "label": "正在营业", "label_en": "Open Now"}
        ]
        
        return {
            "price_levels": price_levels,
            "time_slots": time_slots,
            "sort_options": sort_options,
            "features": features
        }
    finally:
        cursor.close(); db.close()

# ============================================================
# Favorites Endpoints
# ============================================================

@app.get("/api/favorites")
def list_favorites(user: dict = Depends(get_current_user)):
    db = get_db(); cursor = db.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT f.restaurant_id, r.name, r.cover_photo, r.lat, r.lng
            FROM favorites f
            JOIN restaurants r ON f.restaurant_id = r.id
            WHERE f.user_id = %s
        """, (user['uid'],))
        rows = cursor.fetchall()
        return {"data": rows}
    finally: cursor.close(); db.close()

@app.post("/api/favorites/{restaurant_id}")
def toggle_favorite(restaurant_id: int, user: dict = Depends(get_current_user)):
    db = get_db(); cursor = db.cursor(dictionary=True)
    try:
        cursor.execute("SELECT id FROM favorites WHERE user_id = %s AND restaurant_id = %s", (user['uid'], restaurant_id))
        row = cursor.fetchone()
        if row: 
            cursor.execute("DELETE FROM favorites WHERE id = %s", (row['id'],))
            status = "removed"
        else: 
            cursor.execute("INSERT INTO favorites (user_id, restaurant_id) VALUES (%s, %s)", (user['uid'], restaurant_id))
            status = "added"
        db.commit()
        return {"ok": True, "status": status}
    finally: cursor.close(); db.close()

# ============================================================
# Notifications Endpoints
# ============================================================

class RegisterDeviceRequest(BaseModel):
    device_token: str
    device_type: str  # ios, android, huawei
    app_version: Optional[str] = None

@app.post("/api/notifications/register-device")
def register_device(req: RegisterDeviceRequest, user: dict = Depends(verify_token)):
    """注册设备Token用于推送通知"""
    db = get_db(); cursor = db.cursor()
    try:
        # 检查是否已存在
        cursor.execute("SELECT id FROM user_devices WHERE device_token = %s", (req.device_token,))
        existing = cursor.fetchone()
        
        if existing:
            # 更新现有记录
            cursor.execute("""
                UPDATE user_devices 
                SET user_id = %s, device_type = %s, app_version = %s, is_active = 1
                WHERE device_token = %s
            """, (user['uid'], req.device_type, req.app_version, req.device_token))
        else:
            # 插入新记录
            cursor.execute("""
                INSERT INTO user_devices (user_id, device_type, device_token, app_version)
                VALUES (%s, %s, %s, %s)
            """, (user['uid'], req.device_type, req.device_token, req.app_version))
        
        db.commit()
        return {"ok": True, "message": "Device registered successfully"}
    finally: cursor.close(); db.close()


@app.get("/api/notifications")
def list_notifications(
    user: dict = Depends(get_current_user),
    page: int = 1, 
    limit: int = 20,
    unread_only: bool = False
):
    """获取用户通知列表"""
    db = get_db(); cursor = db.cursor(dictionary=True)
    try:
        where = ["user_id = %s"]; params = [user['uid']]
        if unread_only:
            where.append("is_read = 0")
        
        where_str = " AND ".join(where)
        offset = (page - 1) * limit
        
        cursor.execute(f"""
            SELECT * FROM user_notifications 
            WHERE {where_str}
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """, params + [limit, offset])
        rows = cursor.fetchall()
        
        # 解析JSON数据
        for row in rows:
            row['data'] = parse_json_field(row['data'])
        
        # 获取未读数量
        cursor.execute("""
            SELECT COUNT(*) as unread_count 
            FROM user_notifications 
            WHERE user_id = %s AND is_read = 0
        """, (user['uid'],))
        unread_count = cursor.fetchone()['unread_count']
        
        # 获取总数
        cursor.execute(f"SELECT COUNT(*) as total FROM user_notifications WHERE {where_str}", params)
        total = cursor.fetchone()['total']
        
        return {
            "total": total,
            "unread_count": unread_count,
            "page": page,
            "limit": limit,
            "data": rows
        }
    finally: cursor.close(); db.close()


@app.get("/api/notifications/unread-count")
def get_unread_count(user: dict = Depends(get_current_user)):
    """获取用户未读通知数量"""
    db = get_db(); cursor = db.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT COUNT(*) as count 
            FROM user_notifications 
            WHERE user_id = %s AND is_read = 0
        """, (user['uid'],))
        count = cursor.fetchone()['count']
        return {"unread_count": count}
    finally: cursor.close(); db.close()


@app.post("/api/notifications/{notification_id}/read")
def mark_notification_read(notification_id: int, user: dict = Depends(get_current_user)):
    """标记通知为已读"""
    db = get_db(); cursor = db.cursor()
    try:
        cursor.execute("""
            UPDATE user_notifications 
            SET is_read = 1, read_at = NOW()
            WHERE id = %s AND user_id = %s
        """, (notification_id, user['uid']))
        db.commit()
        return {"ok": True, "message": "Marked as read"}
    finally: cursor.close(); db.close()


@app.post("/api/notifications/read-all")
def mark_all_notifications_read(user: dict = Depends(get_current_user)):
    """标记所有通知为已读"""
    db = get_db(); cursor = db.cursor()
    try:
        cursor.execute("""
            UPDATE user_notifications 
            SET is_read = 1, read_at = NOW()
            WHERE user_id = %s AND is_read = 0
        """, (user['uid'],))
        db.commit()
        return {"ok": True, "message": "All notifications marked as read"}
    finally: cursor.close(); db.close()


# ============================================================
# Admin Endpoints
# ============================================================

@app.get("/api/admin/restaurants")
def admin_list_restaurants(
    status: Optional[str] = None,
    verification: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1, limit: int = 50,
    user: dict = Depends(require_admin)
):
    db = get_db(); cursor = db.cursor(dictionary=True)
    try:
        where = ["1=1"]; params = []
        if status: where.append("r.status = %s"); params.append(status)
        if verification: where.append("r.verification_status = %s"); params.append(verification)
        if search:
            q = f"%{search}%"
            where.append("(r.name_zh LIKE %s OR r.name_en LIKE %s OR r.address LIKE %s)")
            params.extend([q, q, q])

        where_str = " AND ".join(where)
        offset = (page - 1) * limit

        cursor.execute(f"SELECT COUNT(*) as total FROM restaurants r WHERE {where_str}", params)
        total = cursor.fetchone()['total']

        cursor.execute(f"""
            SELECT r.*, s.name as state_name, s.name_zh as state_name_zh, a.area as area_name
            FROM restaurants r
            LEFT JOIN states s ON CAST(s.name AS CHAR CHARACTER SET utf8mb4)
                                 = CAST(r.state AS CHAR CHARACTER SET utf8mb4)
            LEFT JOIN areas a ON CAST(a.area AS CHAR CHARACTER SET utf8mb4)
                                = CAST(r.area AS CHAR CHARACTER SET utf8mb4)
            WHERE {where_str}
            ORDER BY r.created_at DESC
            LIMIT %s OFFSET %s
        """, params + [limit, offset])
        rows = [row_to_dict(r) for r in cursor.fetchall()]

        return {"total": total, "page": page, "limit": limit, "data": rows}
    finally: cursor.close(); db.close()

@app.get("/api/admin/stats")
def admin_stats(user: dict = Depends(require_admin)):
    db = get_db(); cursor = db.cursor(dictionary=True)
    # 全局排除新加坡数据
    SG_EXCLUDE = "country = 'MY'"
    try:
        stats = {}
        cursor.execute(f"SELECT COUNT(*) as cnt FROM restaurants WHERE status = 'active' AND {SG_EXCLUDE}")
        stats['total_restaurants'] = cursor.fetchone()['cnt']
        cursor.execute(f"SELECT COUNT(*) as cnt FROM restaurants WHERE status = 'pending' AND {SG_EXCLUDE}")
        stats['pending_count'] = cursor.fetchone()['cnt']
        cursor.execute(f"SELECT COUNT(*) as cnt FROM restaurants WHERE status = 'hidden' AND {SG_EXCLUDE}")
        stats['hidden_count'] = cursor.fetchone()['cnt']
        cursor.execute("SELECT COUNT(*) as cnt FROM users")
        stats['total_users'] = cursor.fetchone()['cnt']
        cursor.execute("SELECT COUNT(*) as cnt FROM reports WHERE status = 'pending'")
        stats['pending_reports'] = cursor.fetchone()['cnt']

        # 各州分布（排除新加坡，按数量降序，只取前20）
        cursor.execute(f"""
            SELECT COALESCE(s.name_zh, r.state, '未知') as name, COUNT(*) as cnt
            FROM restaurants r
            LEFT JOIN states s ON CAST(s.name AS CHAR CHARACTER SET utf8mb4)
                                 = CAST(r.state AS CHAR CHARACTER SET utf8mb4)
            WHERE r.status = 'active' AND {SG_EXCLUDE}
            GROUP BY COALESCE(s.name_zh, r.state)
            ORDER BY cnt DESC
            LIMIT 20
        """)
        stats['by_state'] = cursor.fetchall()

        # 类别分布（排除新加坡）
        cursor.execute(f"""
            SELECT COALESCE(vegetarian_type, '未分类') as category, COUNT(*) as cnt
            FROM restaurants
            WHERE status = 'active' AND {SG_EXCLUDE}
            GROUP BY vegetarian_type
            ORDER BY cnt DESC
        """)
        stats['by_category'] = cursor.fetchall()

        cursor.execute(f"""
            SELECT verification_status, COUNT(*) as cnt
            FROM restaurants
            WHERE {SG_EXCLUDE}
            GROUP BY verification_status
        """)
        stats['by_verification'] = cursor.fetchall()

        return stats
    finally: cursor.close(); db.close()


class SendNotificationRequest(BaseModel):
    user_ids: Optional[List[int]] = None  # 为空则发送给所有用户
    type: str  # new_restaurant, announcement, promotion, update
    title: str
    content: str
    data: Optional[dict] = None  # 额外数据（如餐厅ID）

@app.post("/api/admin/notifications/send")
def admin_send_notification(req: SendNotificationRequest, user: dict = Depends(require_admin)):
    """管理员发送通知给指定用户或所有用户"""
    db = get_db(); cursor = db.cursor()
    try:
        notification_type = req.type if req.type in ['new_restaurant', 'announcement', 'promotion', 'update'] else 'announcement'
        
        if req.user_ids:
            # 发送给指定用户
            for uid in req.user_ids:
                cursor.execute("""
                    INSERT INTO user_notifications (user_id, type, title, content, data)
                    VALUES (%s, %s, %s, %s, %s)
                """, (uid, notification_type, req.title, req.content, json.dumps(req.data) if req.data else None))
            target_count = len(req.user_ids)
        else:
            # 发送给所有用户
            cursor.execute("SELECT id FROM users WHERE is_active = 1")
            all_users = cursor.fetchall()
            for u in all_users:
                cursor.execute("""
                    INSERT INTO user_notifications (user_id, type, title, content, data)
                    VALUES (%s, %s, %s, %s, %s)
                """, (u['id'], notification_type, req.title, req.content, json.dumps(req.data) if req.data else None))
            target_count = len(all_users)
        
        db.commit()
        return {
            "ok": True, 
            "message": f"Notification sent to {target_count} users",
            "target_count": target_count
        }
    finally: cursor.close(); db.close()


@app.post("/api/admin/notifications/new-restaurant/{restaurant_id}")
def admin_notify_new_restaurant(restaurant_id: int, user: dict = Depends(require_admin)):
    """通知所有用户有新餐厅上线"""
    db = get_db(); cursor = db.cursor(dictionary=True)
    try:
        # 获取餐厅信息
        cursor.execute("SELECT name_zh, name_en, area, state FROM restaurants WHERE id = %s", (restaurant_id,))
        restaurant = cursor.fetchone()
        if not restaurant:
            raise HTTPException(status_code=404, detail="Restaurant not found")
        
        restaurant_name = restaurant['name_zh'] or restaurant['name_en'] or 'New Restaurant'
        location = f"{restaurant['area']}, {restaurant['state']}" if restaurant['area'] else restaurant['state']
        
        # 检查是否已发送过通知
        cursor.execute("SELECT id FROM new_restaurant_notifications WHERE restaurant_id = %s", (restaurant_id,))
        if cursor.fetchone():
            return {"ok": False, "message": "Notification already sent for this restaurant"}
        
        # 记录已发送
        cursor.execute("""
            INSERT INTO new_restaurant_notifications (restaurant_id, notification_sent, sent_at)
            VALUES (%s, 1, NOW())
        """, (restaurant_id,))
        
        # 发送给所有用户
        title = f"🎉 新餐厅上线: {restaurant_name}"
        content = f"{location} 新增一家素食餐厅，快来看看！"
        data = {"restaurant_id": restaurant_id, "type": "new_restaurant"}
        
        cursor.execute("SELECT id FROM users WHERE is_active = 1")
        all_users = cursor.fetchall()
        for u in all_users:
            cursor.execute("""
                INSERT INTO user_notifications (user_id, type, title, content, data)
                VALUES (%s, 'new_restaurant', %s, %s, %s)
            """, (u['id'], title, content, json.dumps(data)))
        
        db.commit()
        return {
            "ok": True, 
            "message": f"New restaurant notification sent to {len(all_users)} users",
            "restaurant_name": restaurant_name
        }
    finally: cursor.close(); db.close()


# ============================================================
# Helper Endpoints
# ============================================================

@app.get("/api/notices")
def list_notices(
    type: Optional[str] = None,  # banner, popup
    limit: int = 5
):
    """获取当前活跃的公告/横幅"""
    db = get_db(); cursor = db.cursor(dictionary=True)
    try:
        where = ["is_active = 1", "(deleted_at IS NULL)"]
        params = []
        
        if type:
            where.append("type = %s")
            params.append(type)
        
        where_str = " AND ".join(where)
        
        cursor.execute(f"""
            SELECT id, type, content, info, image_url, link_name, links, priority, created_at
            FROM notices
            WHERE {where_str}
            ORDER BY priority DESC, created_at DESC
            LIMIT %s
        """, params + [limit])
        
        rows = cursor.fetchall()
        for row in rows:
            row['links'] = parse_json_field(row['links'])
        
        return {"data": rows}
    finally: cursor.close(); db.close()


@app.get("/api/states")
def list_states():
    db = get_db(); cursor = db.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT * FROM states 
            WHERE is_active = 1 
            ORDER BY sort_order, name
        """)
        states = cursor.fetchall()
        
        cursor.execute("SELECT state, COUNT(DISTINCT area) as cnt FROM areas GROUP BY state")
        area_counts = {row['state']: row['cnt'] for row in cursor.fetchall()}
        
        for state in states:
            state['area_count'] = area_counts.get(state['name'], 0)
        
        return states
    finally: cursor.close(); db.close()

@app.get("/api/states/{state_id}/areas")
def list_areas(state_id: int):
    db = get_db(); cursor = db.cursor(dictionary=True)
    try:
        cursor.execute("SELECT name FROM states WHERE id = %s", (state_id,))
        state = cursor.fetchone()
        if not state:
            return []
        cursor.execute("SELECT * FROM areas WHERE state = %s ORDER BY name", (state['name'],))
        return cursor.fetchall()
    finally: cursor.close(); db.close()

@app.get("/api/tags")
def list_tags(type: Optional[str] = None):
    db = get_db(); cursor = db.cursor(dictionary=True)
    try:
        where = "WHERE is_active = 1"
        if type: where += f" AND type = '{type}'"
        cursor.execute(f"SELECT * FROM tags {where} ORDER BY type, sort_order, name_en")
        return cursor.fetchall()
    finally: cursor.close(); db.close()

@app.get("/api/photos/{legacy_pid}/{filename}")
async def get_photo(legacy_pid: int, filename: str):
    import httpx
    file_path = os.path.join(PHOTO_DIR, str(legacy_pid), filename)
    if os.path.isfile(file_path):
        return FileResponse(file_path, media_type="image/jpeg")
    remote_url = f"http://goveggiemalaysia.com/foodlogDB_cms/images/vendorPic/{filename}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(remote_url)
            if resp.status_code == 200:
                os.makedirs(os.path.join(PHOTO_DIR, str(legacy_pid)), exist_ok=True)
                with open(file_path, 'wb') as f: f.write(resp.content)
                return Response(content=resp.content, media_type="image/jpeg")
    except: pass
    return {"error": "Not found"}, 404

# ============================================================
# Upload Endpoints
# ============================================================

app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

@app.post("/api/upload")
async def upload_photo(file: UploadFile = File(...), user: dict = Depends(verify_token)):
    import uuid as _uuid
    ext = os.path.splitext(file.filename or "photo.jpg")[1] or ".jpg"
    filename = f"{_uuid.uuid4().hex}{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    content = await file.read()
    with open(filepath, "wb") as f:
        f.write(content)
    url = f"/uploads/{filename}"
    return {"ok": True, "url": url, "filename": filename}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
