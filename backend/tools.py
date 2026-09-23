"""工具函数集合：URL 标题抓取、站点图标识别。"""

import re

import httpx


# ---------------------------------------------------------------------------
# 1. 根据 URL 抓取页面 <title>
# ---------------------------------------------------------------------------

def fetch_page_title(url: str) -> str:
    """用 httpx 请求 URL，提取 <title> 标签内容。

    超时 5 秒；任意异常（网络、解析等）均返回空字符串。
    """
    try:
        resp = httpx.get(url, timeout=5.0, follow_redirects=True)
        resp.raise_for_status()
        # 从 HTML 文本中提取 <title>...</title>
        m = re.search(r"<title[^>]*>(.*?)</title>", resp.text, re.IGNORECASE | re.DOTALL)
        if m:
            return m.group(1).strip()
    except Exception:
        pass
    return ""


# ---------------------------------------------------------------------------
# 2. 根据 URL 域名 / 路径返回 emoji 图标
# ---------------------------------------------------------------------------

_ICON_RULES: list[tuple[str, str]] = [
    # (匹配关键字, emoji)
    ("github",       "🐙"),
    ("google",       "🔍"),
    ("mail",         "📧"),
    ("gmail",        "📧"),
    ("youtube",      "📺"),
    ("bilibili",     "📺"),
    ("twitter",      "🐦"),
    ("weibo",        "🐦"),
    ("stackoverflow","📚"),
    ("csdn",         "📚"),
    ("juejin",       "📚"),
    ("aws",          "☁️"),
    ("aliyun",       "☁️"),
    ("cloud",        "☁️"),
]


def detect_icon_from_url(url: str) -> str:
    """根据 URL 域名/路径返回合适的 emoji，无匹配返回 🌐。"""
    lower = url.lower()
    for keyword, emoji in _ICON_RULES:
        if keyword in lower:
            return emoji
    return "🌐"


# ---------------------------------------------------------------------------
# 自测
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_urls = [
        "https://github.com",
        "https://www.google.com",
        "https://mail.google.com",
        "https://www.youtube.com",
        "https://aws.amazon.com",
        "https://example.com",
    ]

    print("=" * 50)
    print("页面标题 & 图标测试")
    print("=" * 50)

    for u in test_urls:
        icon = detect_icon_from_url(u)
        title = fetch_page_title(u)
        print(f"{icon}  {u}")
        print(f"   标题: {title or '(无标题/请求失败)'}")
        print()
