"""
NeuNav 2.0 · 灵境 — 国风智境导航
FastAPI + Vue3 + Canvas 山水 + SQLite
"""
import os, json, math
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3

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
            created_at TEXT DEFAULT (datetime('now'))
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
    uvicorn.run(app, host="0.0.0.0", port=8011)
