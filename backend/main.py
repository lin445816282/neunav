"""
NeuNav 2.0 · 灵境 — 国风智境导航
FastAPI + Vue3 + Canvas 山水 + SQLite
"""
import os, json, math, hashlib
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3
import requests

# ── 微信小程序配置 ──
WX_APPID = "wxe0e4731ec351bfe3"
WX_SECRET = "c2698a2b7934f33a3d3d603a26c536fe"

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "data" / "neunav.db"
os.makedirs(BASE_DIR / "data", exist_ok=True)

app = FastAPI(title="NeuNav 灵境", version="2.0", docs_url=None, redoc_url=None)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── DB ──────────────────────────────────────
def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            icon TEXT DEFAULT '📁',
            sort_order INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            is_guest INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS bookmarks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER REFERENCES categories(id),
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            icon TEXT DEFAULT '🔗',
            description TEXT DEFAULT '',
            visit_count INTEGER DEFAULT 0,
            sort_score REAL DEFAULT 0,
            last_visited TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_bm_cat ON bookmarks(category_id);
        CREATE TABLE IF NOT EXISTS user_settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS mood_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT DEFAULT (datetime('now'))
        );
        INSERT OR IGNORE INTO user_settings (key, value) VALUES ('ink_mode', 'light');
        INSERT OR IGNORE INTO user_settings (key, value) VALUES ('mountain_intensity', '0.6');
        INSERT OR IGNORE INTO user_settings (key, value) VALUES ('theme', 'ink');
        CREATE TABLE IF NOT EXISTS unscrew_lb (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            openid TEXT NOT NULL,
            nick TEXT DEFAULT '萌糖玩家',
            score INTEGER DEFAULT 0,
            level INTEGER DEFAULT 1,
            stars INTEGER DEFAULT 1,
            efficiency INTEGER DEFAULT 0,
            coins INTEGER DEFAULT 0,
            title TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            is_guest INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_unscrew_lb_score ON unscrew_lb(score DESC);
        CREATE INDEX IF NOT EXISTS idx_unscrew_lb_openid ON unscrew_lb(openid);
    """)
    conn.commit()
    conn.close()

# ── Migration: ensure deleted_at columns exist ──
_mig = get_db()
try:
    _mig.execute("ALTER TABLE bookmarks ADD COLUMN deleted_at TEXT")
except sqlite3.OperationalError:
    pass
try:
    _mig.execute("ALTER TABLE categories ADD COLUMN deleted_at TEXT")
except sqlite3.OperationalError:
    pass
try:
    _mig.execute("CREATE INDEX IF NOT EXISTS idx_bm_deleted ON bookmarks(deleted_at)")
except sqlite3.OperationalError:
    pass
try:
    _mig.execute("ALTER TABLE unscrew_lb ADD COLUMN coins INTEGER DEFAULT 0")
except sqlite3.OperationalError:
    pass
try:
    _mig.execute("ALTER TABLE unscrew_lb ADD COLUMN title TEXT DEFAULT ''")
except sqlite3.OperationalError:
    pass
_mig.commit()
_mig.close()

init_db()

# ── Ambiance Engine ─────────────────────────
# 节气计算（精确到日）
SOLAR_TERMS_2026 = [
    (1, 5, "小寒"), (1, 20, "大寒"), (2, 4, "立春"), (2, 18, "雨水"),
    (3, 5, "惊蛰"), (3, 20, "春分"), (4, 4, "清明"), (4, 19, "谷雨"),
    (5, 5, "立夏"), (5, 20, "小满"), (6, 5, "芒种"), (6, 21, "夏至"),
    (7, 7, "小暑"), (7, 22, "大暑"), (8, 7, "立秋"), (8, 22, "处暑"),
    (9, 7, "白露"), (9, 22, "秋分"), (10, 7, "寒露"), (10, 23, "霜降"),
    (11, 7, "立冬"), (11, 21, "小雪"), (12, 6, "大雪"), (12, 21, "冬至"),
]

MOON_PHASES = ["🌑 朔", "🌒 上弦", "🌓 盈凸", "🌕 望", "🌖 亏凸", "🌗 下弦", "🌘 残"]

# 时辰对应诗词
HOUR_POEMS = {
    0: "夜深千帐灯 — 纳兰性德",
    1: "星垂平野阔 — 杜甫",
    2: "月落乌啼霜满天 — 张继",
    3: "北斗阑干南斗斜 — 刘方平",
    4: "鸡鸣紫陌曙光寒 — 岑参",
    5: "东方欲晓，莫道君行早 — 毛泽东",
    6: "日出江花红胜火 — 白居易",
    7: "清晨入古寺 — 常建",
    8: "晴空一鹤排云上 — 刘禹锡",
    9: "白日依山尽 — 王之涣",
    10: "日照香炉生紫烟 — 李白",
    11: "云淡风轻近午天 — 程颢",
    12: "锄禾日当午 — 李绅",
    13: "日长睡起无情思 — 杨万里",
    14: "山光忽西落 — 孟浩然",
    15: "夕阳无限好 — 李商隐",
    16: "一道残阳铺水中 — 白居易",
    17: "落霞与孤鹜齐飞 — 王勃",
    18: "暮从碧山下 — 李白",
    19: "月上柳梢头 — 欧阳修",
    20: "天阶夜色凉如水 — 杜牧",
    21: "灯火阑珊处 — 辛弃疾",
    22: "姑苏城外寒山寺 — 张继",
    23: "夜半钟声到客船 — 张继",
}

def get_solar_term(dt: datetime) -> str:
    for m, d, name in SOLAR_TERMS_2026:
        term_date = datetime(2026, m, d)
        if dt >= term_date:
            current = name
    return current

def get_hour_color(hour: int) -> dict:
    """时辰→颜色映射"""
    if 5 <= hour < 8:
        return {"bg1": "#f0e6d3", "bg2": "#d4a574", "ink": "#3b2210", "accent": "#8b4513"}
    elif 8 <= hour < 17:
        return {"bg1": "#e8f0e3", "bg2": "#a8c8a0", "ink": "#1a3a1a", "accent": "#2d5a27"}
    elif 17 <= hour < 20:
        return {"bg1": "#f5e6d3", "bg2": "#e8a87c", "ink": "#4a2020", "accent": "#c03020"}
    else:
        return {"bg1": "#1a1a2e", "bg2": "#16213e", "ink": "#e0d8c0", "accent": "#c9a84c"}

@app.get("/api/ambiance")
async def get_ambiance():
    now = datetime.now()
    hour = now.hour
    solar_term = get_solar_term(now)
    # 月相简化：每月15=满月，按天线性插值
    moon_day = now.day
    if moon_day <= 15:
        phase_idx = min(int(moon_day / 15 * 3), 3)
    else:
        phase_idx = 3 + min(int((moon_day - 15) / 15 * 3), 3)
    moon_phase = MOON_PHASES[phase_idx]
    
    colors = get_hour_color(hour)
    poem = HOUR_POEMS.get(hour, "行到水穷处，坐看云起时 — 王维")
    
    return {
        "hour": hour,
        "solar_term": solar_term,
        "moon_phase": moon_phase,
        "poem": poem,
        "colors": colors,
        "mountain_intensity": 0.6,
        "brush_style": "sharp" if 8 <= hour <= 16 else "soft",
    }

# ── API: Categories ─────────────────────────
@app.get("/api/categories")
async def list_categories():
    conn = get_db()
    rows = [dict(r) for r in conn.execute("SELECT * FROM categories WHERE deleted_at IS NULL ORDER BY sort_order, id").fetchall()]
    conn.close()
    return {"categories": rows}

class CatCreate(BaseModel):
    name: str
    icon: str = "📁"
    sort_order: int = 0

@app.post("/api/categories")
async def add_category(c: CatCreate):
    conn = get_db()
    conn.execute("INSERT INTO categories (name, icon, sort_order) VALUES (?,?,?)", (c.name, c.icon, c.sort_order))
    conn.commit()
    conn.close()
    return {"ok": True}

@app.delete("/api/categories/{cid}")
async def del_category(cid: int):
    conn = get_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("UPDATE categories SET deleted_at=? WHERE id=?", (now, cid))
    conn.execute("UPDATE bookmarks SET deleted_at=? WHERE category_id=? AND deleted_at IS NULL", (now, cid))
    conn.commit()
    conn.close()
    return {"ok": True}

# ── API: Bookmarks ──────────────────────────
@app.get("/api/bookmarks")
async def list_bookmarks(search: str = "", category_id: int = 0, limit: int = 100):
    conn = get_db()
    if search:
        rows = conn.execute(
            "SELECT * FROM bookmarks WHERE deleted_at IS NULL AND (title LIKE ? OR url LIKE ?) ORDER BY sort_score DESC, visit_count DESC LIMIT ?",
            (f"%{search}%", f"%{search}%", limit)
        ).fetchall()
    elif category_id:
        rows = conn.execute("SELECT * FROM bookmarks WHERE deleted_at IS NULL AND category_id=? ORDER BY sort_score DESC", (category_id,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM bookmarks WHERE deleted_at IS NULL ORDER BY sort_score DESC, visit_count DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return {"bookmarks": [dict(r) for r in rows]}

class BmCreate(BaseModel):
    category_id: int = 0
    title: str
    url: str
    icon: str = "🔗"
    description: str = ""

@app.post("/api/bookmarks")
async def add_bookmark(b: BmCreate):
    conn = get_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "INSERT INTO bookmarks (category_id, title, url, icon, description, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
        (b.category_id, b.title, b.url, b.icon, b.description, now, now)
    )
    conn.commit()
    conn.close()
    return {"ok": True}

@app.put("/api/bookmarks/{bid}/visit")
async def visit_bookmark(bid: int):
    conn = get_db()
    bm = conn.execute("SELECT * FROM bookmarks WHERE id=?", (bid,)).fetchone()
    if bm:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("UPDATE bookmarks SET visit_count=visit_count+1, last_visited=?, sort_score=sort_score+1, updated_at=? WHERE id=?", (now, now, bid))
        conn.commit()
    conn.close()
    return {"ok": True}

@app.delete("/api/bookmarks/{bid}")
async def del_bookmark(bid: int):
    conn = get_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("UPDATE bookmarks SET deleted_at=? WHERE id=?", (now, bid))
    conn.commit()
    conn.close()
    return {"ok": True}

class BmUpdate(BaseModel):
    title: str = None
    url: str = None
    icon: str = None
    category_id: int = None

@app.put("/api/bookmarks/reorder")
async def reorder_bookmarks(request: Request):
    body = await request.json()
    items = body.get("items", [])
    conn = get_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for item in items:
        conn.execute(
            "UPDATE bookmarks SET sort_score=?, updated_at=? WHERE id=?",
            (item["sort_score"], now, item["id"])
        )
    conn.commit()
    conn.close()
    return {"ok": True}

@app.put("/api/bookmarks/{bid}")
async def update_bookmark(bid: int, b: BmUpdate):
    conn = get_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sets = []
    vals = []
    if b.title is not None: sets.append("title=?"); vals.append(b.title)
    if b.url is not None: sets.append("url=?"); vals.append(b.url)
    if b.icon is not None: sets.append("icon=?"); vals.append(b.icon)
    if b.category_id is not None: sets.append("category_id=?"); vals.append(b.category_id)
    if sets:
        sets.append("updated_at=?")
        vals.append(now)
        vals.append(bid)
        conn.execute(f"UPDATE bookmarks SET {', '.join(sets)} WHERE id=?", vals)
        conn.commit()
    conn.close()
    return {"ok": True}

class CatUpdate(BaseModel):
    name: str = None
    icon: str = None

@app.put("/api/categories/{cid}")
async def update_category(cid: int, c: CatUpdate):
    conn = get_db()
    sets = []
    vals = []
    if c.name is not None: sets.append("name=?"); vals.append(c.name)
    if c.icon is not None: sets.append("icon=?"); vals.append(c.icon)
    if sets:
        vals.append(cid)
        conn.execute(f"UPDATE categories SET {', '.join(sets)} WHERE id=?", vals)
        conn.commit()
    conn.close()
    return {"ok": True}

# ── API: Settings ───────────────────────────
@app.get("/api/settings")
async def get_settings():
    conn = get_db()
    rows = conn.execute("SELECT * FROM user_settings").fetchall()
    conn.close()
    return {"settings": {r["key"]: r["value"] for r in rows}}

@app.put("/api/settings/{key}")
async def update_setting(key: str, request: Request):
    body = await request.json()
    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO user_settings (key, value, updated_at) VALUES (?,?,datetime('now'))", (key, str(body.get("value", ""))))
    conn.commit()
    conn.close()
    return {"ok": True}

# ── 🔧 Hermes 自救 API ──────────────────────
import subprocess

HERMES_CONFIG = os.path.expanduser("~/.hermes/config.yaml")
DIRECT_URL_DS = "https://api.deepseek.com/v1"
DIRECT_URL_KIMI = "https://api.moonshot.cn/v1"
PROXY_URL = "http://localhost:8100/v1"

# 预设配置：按模式名提供完整的 model 三段
MODE_PRESETS = {
    "ds-direct": {"provider": "deepseek", "base_url": DIRECT_URL_DS, "default": "deepseek-v4-pro"},
    "ds-proxy":  {"provider": "deepseek", "base_url": PROXY_URL, "default": "deepseek-v4-pro"},
    "kimi-k3":   {"provider": "openai", "base_url": DIRECT_URL_KIMI, "default": "kimi-k3"},
    "kimi-k25":  {"provider": "openai", "base_url": DIRECT_URL_KIMI, "default": "kimi-k2.5"},
    "kimi-fast": {"provider": "openai", "base_url": DIRECT_URL_KIMI, "default": "moonshot-v1-8k"},
}

@app.get("/api/rescue/status")
def rescue_status():
    """获取当前状态"""
    # 检查代理（用 socket，不用异步 httpx 避免事件循环冲突）
    proxy_alive = False
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        proxy_alive = s.connect_ex(('127.0.0.1', 8100)) == 0
        s.close()
    except:
        pass

    # 读当前 Hermes 配置
    cfg = {"provider": "", "base_url": "", "model": ""}
    try:
        with open(HERMES_CONFIG) as f:
            for line in f:
                s = line.strip()
                if s.startswith("provider:"):
                    cfg["provider"] = s.split(":",1)[1].strip()
                elif s.startswith("base_url:"):
                    cfg["base_url"] = s.split(":",1)[1].strip()
                elif s.startswith("default:"):
                    cfg["model"] = s.split(":",1)[1].strip()
    except:
        pass

    # 推断当前模式
    mode_name = "未知"
    if "moonshot" in cfg["base_url"]:
        mode_name = f"Kimi {cfg['model']}"
    elif "deepseek" in cfg["base_url"]:
        if "localhost" in cfg["base_url"]:
            mode_name = "DeepSeek(代理)"
        else:
            mode_name = f"DeepSeek {cfg['model']}"

    hermes_running = False
    try:
        result = subprocess.run(["pgrep", "-f", "hermes.*gateway"], capture_output=True, text=True, timeout=2)
        hermes_running = bool(result.stdout.strip())
    except:
        pass

    # Kimi key 状态
    kimi_configured = False
    try:
        with open(os.path.expanduser("~/.hermes/.env")) as f:
            for line in f:
                if line.startswith("KIMI_API_KEY=") and len(line.strip().split("=",1)[1]) > 10:
                    kimi_configured = True
                    break
    except:
        pass

    return {
        "proxy_alive": proxy_alive,
        "current_mode": mode_name,
        "current_url": cfg["base_url"],
        "current_model": cfg["model"],
        "current_provider": cfg["provider"],
        "hermes_running": hermes_running,
        "kimi_configured": kimi_configured,
    }

# ═══════════════════ 萌糖消了个消 · 排行榜 API ═══════════════════

class UnscrewScoreReq(BaseModel):
    code: str  # wx.login code
    nick: str = "萌糖玩家"
    score: int = 0
    level: int = 1
    stars: int = 1
    efficiency: int = 0
    coins: int = 0
    title: str = ""
    is_guest: int = 0  # 0=登录用户 1=游客

@app.post("/api/unscrew/submit")
def unscrew_submit(req: UnscrewScoreReq):
    """提交分数：wx.login code → openId → 存榜"""
    import time as _time
    print(f"[unscrew] submit: nick={req.nick!r} score={req.score} is_guest={req.is_guest}")
    # 1. 用 code 换 openId
    wx_url = f"https://api.weixin.qq.com/sns/jscode2session?appid={WX_APPID}&secret={WX_SECRET}&js_code={req.code}&grant_type=authorization_code"
    try:
        r = requests.get(wx_url, timeout=5)
        wx_data = r.json()
        openid = wx_data.get("openid")
        if not openid:
            return {"ok": False, "error": f"wx auth failed: {wx_data.get('errmsg','unknown')}"}
    except Exception as e:
        return {"ok": False, "error": f"wx request failed: {str(e)}"}

    # 2. 每人只保留最高分
    conn = get_db()
    existing = conn.execute("SELECT id, score FROM unscrew_lb WHERE openid=? AND is_guest=? ORDER BY score DESC LIMIT 1", (openid, req.is_guest)).fetchone()
    if existing and existing["score"] >= req.score:
        print(f"[unscrew] submit SKIP: existing_score={existing['score']} >= new={req.score} (openid={openid}, is_guest={req.is_guest})")
        conn.close()
        return {"ok": True, "kept_existing": True, "openid": openid}

    # 3. 插入/更新纪录（用 upsert 避免与 save 端点的 UNIQUE 约束冲突）
    conn.execute("""
        INSERT INTO unscrew_lb (openid, nick, score, level, stars, efficiency, coins, title, is_guest, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,datetime('now','localtime'))
        ON CONFLICT(openid, is_guest) DO UPDATE SET
            nick=excluded.nick,
            score=excluded.score,
            level=excluded.level,
            stars=excluded.stars,
            efficiency=excluded.efficiency,
            coins=excluded.coins,
            title=excluded.title,
            created_at=datetime('now','localtime')
    """, (openid, req.nick, req.score, req.level, req.stars, req.efficiency, req.coins, req.title, req.is_guest))
    conn.commit()
    print(f"[unscrew] submit UPSERT: nick={req.nick!r} score={req.score} is_guest={req.is_guest} openid={openid}")

    # 4. 清理旧低分（按 openid + is_guest 分组）
    conn.execute("DELETE FROM unscrew_lb WHERE openid=? AND is_guest=? AND id NOT IN (SELECT id FROM unscrew_lb WHERE openid=? AND is_guest=? ORDER BY score DESC LIMIT 1)", (openid, req.is_guest, openid, req.is_guest))
    conn.commit()
    conn.close()

    return {"ok": True, "openid": openid}

@app.get("/api/unscrew/leaderboard")
def unscrew_leaderboard(period: str = "all", limit: int = 50):
    """获取排行榜"""
    conn = get_db()
    if period == "today":
        # 北京时间当天：date(created_at) = 北京时间今天
        rows = conn.execute(
            "SELECT openid, nick, score, level, stars, efficiency, title, created_at, is_guest FROM unscrew_lb WHERE date(created_at) = date('now','localtime') ORDER BY score DESC LIMIT ?",
            (limit,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT openid, nick, score, level, stars, efficiency, title, created_at, is_guest FROM unscrew_lb ORDER BY score DESC LIMIT ?",
            (limit,)
        ).fetchall()
    conn.close()
    return {
        "ok": True,
        "list": [dict(r) for r in rows],
        "total": len(rows)
    }

@app.post("/api/unscrew/save")
def unscrew_save(req: UnscrewScoreReq):
    """保存用户游戏进度"""
    import time as _time
    wx_url = f"https://api.weixin.qq.com/sns/jscode2session?appid={WX_APPID}&secret={WX_SECRET}&js_code={req.code}&grant_type=authorization_code"
    try:
        r = requests.get(wx_url, timeout=5)
        wx_data = r.json()
        openid = wx_data.get("openid")
        if not openid:
            print(f"[unscrew] wx login failed: {wx_data}")
            return {"ok": False, "error": "wx login failed", "detail": wx_data}
    except Exception as e:
        print(f"[unscrew] wx timeout/error: {e}")
        return {"ok": False, "error": "wx timeout"}
    
    conn = get_db()
    try:
        # upsert: 每人只保留一条进度记录
        conn.execute("""
            INSERT INTO unscrew_lb (openid, nick, score, level, stars, efficiency, coins, is_guest, created_at)
            VALUES (?,?,?,?,?,?,?,?,datetime('now','localtime'))
            ON CONFLICT(openid, is_guest) DO UPDATE SET
                nick=excluded.nick,
                score=MAX(score, excluded.score),
                level=MAX(level, excluded.level),
                stars=excluded.stars,
                efficiency=excluded.efficiency,
                coins=excluded.coins,
                created_at=datetime('now','localtime')
        """, (openid, req.nick, req.score, req.level, req.stars, req.efficiency, req.coins, req.is_guest))
        conn.commit()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}
    finally:
        conn.close()

@app.get("/api/unscrew/load")
def unscrew_load(code: str = "", is_guest: int = 0):
    """加载用户游戏进度"""
    import time as _time
    wx_url = f"https://api.weixin.qq.com/sns/jscode2session?appid={WX_APPID}&secret={WX_SECRET}&js_code={code}&grant_type=authorization_code"
    try:
        r = requests.get(wx_url, timeout=5)
        wx_data = r.json()
        openid = wx_data.get("openid")
        if not openid:
            print(f"[unscrew] wx login failed: {wx_data}")
            return {"ok": False, "error": "wx login failed", "detail": wx_data}
    except Exception as e:
        print(f"[unscrew] wx timeout/error: {e}")
        return {"ok": False, "error": "wx timeout"}
    
    conn = get_db()
    row = conn.execute(
        "SELECT score, level, stars, efficiency, coins, nick, is_guest FROM unscrew_lb WHERE openid=? AND is_guest=? ORDER BY id DESC LIMIT 1",
        (openid, is_guest)
    ).fetchone()
    conn.close()
    if row:
        return {"ok": True, "data": dict(row)}
    return {"ok": False, "error": "no data"}

# ═══════════════════ Rescue ═══════════════════

@app.post("/api/rescue/switch")
def rescue_switch(mode: str = "ds-direct"):
    """切换模式: ds-direct | ds-proxy | kimi-k3 | kimi-k25 | kimi-fast"""
    preset = MODE_PRESETS.get(mode)
    if not preset:
        return {"ok": False, "error": f"未知模式: {mode}，可选: {list(MODE_PRESETS.keys())}"}
    
    try:
        content = open(HERMES_CONFIG).read()
        import re
        content = re.sub(r'provider:\s*\S+', f'provider: {preset["provider"]}', content)
        content = re.sub(r'base_url:\s*\S+', f'base_url: {preset["base_url"]}', content)
        content = re.sub(r'default:\s*\S+', f'default: {preset["default"]}', content)
        open(HERMES_CONFIG, 'w').write(content)
        return {"ok": True, "mode": mode, "provider": preset["provider"], "model": preset["default"]}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.post("/api/rescue/restart")
def rescue_restart(target: str = "hermes"):
    """重启服务: hermes | proxy | tunnel"""
    results = []
    if target == "hermes":
        try:
            subprocess.run(["pkill", "-f", "hermes.*gateway"], timeout=5)
            results.append("hermes killed, waiting for auto-restart")
        except:
            results.append("hermes not found")
    elif target == "proxy":
        try:
            subprocess.run(["pkill", "-f", "main.py.*8100"], timeout=5)
            import time; time.sleep(1)
            # 从环境变量或 ~/.keys.env 读 DeepSeek key（不硬编码）
            _dk = os.environ.get("DEEPSEEK_API_KEY", "")
            if not _dk:
                try:
                    for _p in (os.path.expanduser("~/.keys.env"), "/home/xiaolin/.keys.env"):
                        with open(_p) as _f:
                            for _ln in _f:
                                if _ln.strip().startswith("DEEPSEEK_API_KEY="):
                                    _dk = _ln.strip().split("=", 1)[1].strip()
                                    break
                        if _dk:
                            break
                except Exception:
                    pass
            subprocess.Popen(
                ["/home/xiaolin/projects/stock-aggregator/venv/bin/python3", "main.py"],
                cwd="/home/xiaolin/projects/deepseek-tracker/backend",
                env={**os.environ, "DEEPSEEK_API_KEY": _dk},
                start_new_session=True,
            )
            results.append("proxy restarted")
        except Exception as e:
            results.append(f"proxy restart failed: {e}")
    elif target == "tunnel":
        try:
            subprocess.run(["pkill", "-f", "cloudflared tunnel"], timeout=5)
            import time; time.sleep(2)
            subprocess.Popen(
                ["cloudflared", "tunnel", "--config",
                 os.path.expanduser("~/.cloudflared/config.yml"), "run", "stock-tunnel"],
                start_new_session=True,
            )
            results.append("tunnel restarted")
        except Exception as e:
            results.append(f"tunnel restart failed: {e}")
    return {"ok": True, "results": results}


# ── Static + SPA ────────────────────────────
STATIC_DIR = BASE_DIR / "static"

@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")

@app.get("/{path:path}")
async def serve_static(path: str):
    fp = STATIC_DIR / path
    if fp.is_file():
        return FileResponse(fp)
    return FileResponse(STATIC_DIR / "index.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8011, root_path="/neunav")
