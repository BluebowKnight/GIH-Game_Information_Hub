#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
宝可梦简中卡牌情报站 —— 官方数据抓取脚本

数据源（全部为宝可梦中国官方网站 www.pokemon.cn）：
  1. 商品一览        https://www.pokemon.cn/products_category/products/p/22
  2. 卡牌最新资讯    https://www.pokemon.cn/tcg  （分页 /tcg/p/N，含 Product/Campaign/Event/Column/Other）
  3. 官方店铺        https://www.pokemon.cn/shop-home （官方卡牌道馆 / 官方快闪店 / 线上渠道）
  4. 赛制页面        https://www.pokemon.cn/tcg/rules/regulation/ （标准赛制 / 开放赛制）

输出：
  data/data.json   —— 结构化数据
  data/data.js     —— window.PB_DATA = {...}（供 file:// 直接打开，绕过 fetch 的 CORS 限制）
  assets/img/*.webp —— 本地化图片

注意：官网图片 URL 带时效性签名（auth_key），数小时后即失效并 302 跳回首页。
因此抓取时必须把图片下载到本地并压缩，网页只引用本地图片。

用法：
  python3 scripts/fetch_data.py            # 抓取并写入 data/
  python3 scripts/fetch_data.py --dry-run  # 只打印统计，不写文件
  python3 scripts/fetch_data.py --no-image # 跳过图片下载（调试用）
"""

import argparse
import html as htmlmod
import json
import os
import re
import sys
import time
from datetime import datetime, timezone, timedelta

import urllib.request
import urllib.error

BASE = "https://www.pokemon.cn"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

URL_PRODUCTS = f"{BASE}/products_category/products/p/22"
URL_TCG = f"{BASE}/tcg"
URL_SHOP = f"{BASE}/shop-home"
URL_REGULATION = f"{BASE}/tcg/rules/regulation/"
# 按分类的归档（用于精准定位赛事结果与周边商品）
URL_TCG_EVENT = f"{BASE}/category/tcg/event"
URL_GOODS = f"{BASE}/category/goods"

# 新品 / 上新栏目只看这个时间窗内发售（或即将发售）的商品
RECENT_DAYS = 90         # 近 3 个月

# 环境牌组分析底稿（人工维护）：AREAZERO.GG 量化数据 + 潜力判断
META_ANALYSIS = json.load(open(
    os.path.join(SCRIPT_DIR, "meta_analysis.json"), encoding="utf-8"))

# 道馆限定商品底稿（人工维护）：来源 52poke 百科，按吉祥物匹配
_gym_excl_data = json.load(open(
    os.path.join(SCRIPT_DIR, "gym_exclusives.json"), encoding="utf-8"))
GYM_COMMON_EXCLUSIVES = _gym_excl_data.get("_common_exclusives", [])
GYM_EXCL_ENTRIES = _gym_excl_data.get("entries", {})

# 归档页抓取页数（每页约 16 条）
ARCHIVE_PAGES = 10       # 卡牌综合资讯（约近半年）
EVENT_PAGES = 38         # 赛事活动分类归档（回溯历史赛事结果公告）
GOODS_PAGES = 2          # 周边商品资讯（该频道更新较慢）

# 周边商品子分类
GOODS_CATS = [
    ("home-office", "生活杂货"),
    ("plush-toys", "玩具玩偶"),
    ("clothing-accesoies", "衣服饰品"),
    ("stationaries", "文具"),
    ("food", "食品"),
    ("goods-other", "其他"),
]

# 商品内容里出现的「随附周边」关键词，用于在商品卡上打标签
BUNDLED_GOODS_KW = ["冰箱贴", "徽章", "磁吸贴", "挂饰", "贴纸", "卡套", "收纳盒",
                    "手办", "毛绒", "钥匙扣", "玩偶", "卡垫", "展示框", "硬币"]

CST = timezone(timedelta(hours=8))


# ----------------------------------------------------------------------------
# 基础工具
# ----------------------------------------------------------------------------
def get(url, retries=3, timeout=30):
    """抓取网页，返回文本。"""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            })
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
            for enc in ("utf-8", "gbk", "latin-1"):
                try:
                    return raw.decode(enc)
                except UnicodeDecodeError:
                    continue
            return raw.decode("utf-8", "ignore")
        except Exception as exc:  # noqa: BLE001
            if attempt == retries - 1:
                print(f"  [!] 抓取失败 {url}: {exc}", file=sys.stderr)
                return ""
            time.sleep(2 * (attempt + 1))
    return ""


def clean(text):
    """去标签、解压实体、压空白。"""
    if not text:
        return ""
    # 官网页面偶尔残留未渲染的 JS 模板字面量（如 ${product.content || ''}）
    text = re.sub(r"\$\{[^}]*\}", "", text)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = htmlmod.unescape(text)
    text = re.sub(r"[ \t　]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def strip_img_auth(url):
    """去掉图片 URL 上带时效的 auth_key 参数，避免缓存后失效。"""
    if not url:
        return ""
    return re.sub(r"[?&]auth_key=[^&]*", "", url).replace("?&", "?").rstrip("?")


def to_abs(url):
    if not url:
        return ""
    url = url.strip()
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        return BASE + url
    return url


# ----------------------------------------------------------------------------
# 图片本地化
# ----------------------------------------------------------------------------
IMG_SPECS = {
    "product": (520, 82),   # 商品图：宽 520，质量 82
    "card": (420, 80),      # 资讯缩略图
    "shop": (360, 78),      # 道馆/店铺图
}

SKIP_IMAGE = False
IMG_DIR = ""          # 由 main() 赋值
IMG_KEEP_DAYS = 45    # 超过该天数未被刷新的本地图片自动清理
_IMG_CACHE = {}


def ensure_pillow():
    try:
        from PIL import Image  # noqa: F401
        return True
    except ImportError:
        return False


def localize_image(url, kind="card"):
    """下载远端图片 → 压缩为 webp → 返回本地相对路径。

    失败时返回空字符串（页面将显示占位图）。
    文件名哈希基于「去掉 auth_key 的 URL」，保证每周抓取命中同一文件、不重复下载。
    """
    if not url or SKIP_IMAGE or not IMG_DIR:
        return ""
    if url.startswith("data:") or url.startswith("assets/"):
        return url
    # 只本地化官网图床的图片，外链（如视频平台封面）不下载
    if "pokemon.com.cn" not in url and "pokemon.cn" not in url:
        return ""
    if url in _IMG_CACHE:
        return _IMG_CACHE[url]

    import hashlib
    from PIL import Image
    from io import BytesIO

    width, quality = IMG_SPECS.get(kind, IMG_SPECS["card"])
    stable = strip_img_auth(url)  # 去掉时效签名，稳定标识
    digest = hashlib.md5(stable.encode("utf-8")).hexdigest()[:16]
    fname = f"{kind}_{digest}.webp"
    rel = "assets/img/" + fname
    path = os.path.join(IMG_DIR, fname)

    if os.path.exists(path) and os.path.getsize(path) > 0:
        _IMG_CACHE[url] = rel
        return rel

    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": UA,
            "Referer": "https://www.pokemon.cn/",
        })
        with urllib.request.urlopen(req, timeout=40) as resp:
            raw = resp.read()
        img = Image.open(BytesIO(raw))
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGBA")
        else:
            img = img.convert("RGB")
        w, h = img.size
        if w > width:
            img = img.resize((width, max(1, int(h * width / w))), Image.LANCZOS)
        img.save(path, "WEBP", quality=quality, method=4)
        _IMG_CACHE[url] = rel
        return rel
    except Exception as exc:  # noqa: BLE001
        print(f"  [!] 图片下载失败 {url[:80]}...: {exc}", file=sys.stderr)
        _IMG_CACHE[url] = ""
        return ""


def parse_cn_date(text):
    """把 '2026年9月16日' / '2026年9月16日10时起' 等解析为 date 与时间戳。"""
    if not text:
        return None, 0
    m = re.search(r"(\d{4})[年\-/.](\d{1,2})[月\-/.](\d{1,2})", text)
    if not m:
        return None, 0
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        dt = datetime(y, mo, d, tzinfo=CST)
    except ValueError:
        return None, 0
    return dt.strftime("%Y-%m-%d"), int(dt.timestamp())


# ----------------------------------------------------------------------------
# 1. 商品一览（新品 / 上新）
# ----------------------------------------------------------------------------
PRODUCT_TABS = [
    ("expansionPack", "补充包"),
    ("constructionDeck", "构筑卡组"),
    ("otherItems", "礼盒套装"),
    ("surroundingGoods", "周边道具"),
]


def fetch_products():
    """解析商品一览页四个分类：补充包 / 构筑卡组 / 礼盒套装 / 周边道具。"""
    page = get(URL_PRODUCTS)
    if not page:
        return []

    # 按 tab 切段
    segments = {}
    marks = [(tab, page.find(f'id="productsTab_{tab}"')) for tab, _ in PRODUCT_TABS]
    marks = [(t, i) for t, i in marks if i >= 0]
    marks.sort(key=lambda x: x[1])
    for idx, (tab, start) in enumerate(marks):
        end = marks[idx + 1][1] if idx + 1 < len(marks) else len(page)
        segments[tab] = page[start:end]

    out = []
    for tab, cn_name in PRODUCT_TABS:
        seg = segments.get(tab, "")
        # 以 <li class="List_item"> 切分，避免 Description-list 里的 </li> 提前截断
        chunks = seg.split('<li class="List_item">')[1:]
        for chunk in chunks:
            title_m = re.search(r'<div class="Title">(.*?)</div>', chunk, re.S)
            if not title_m:
                continue
            title = clean(title_m.group(1))
            if not title:
                continue

            # 图片（保留带签名的原始 URL 用于下载）
            img_m = re.search(r'<img class="After_load"[^>]*src="([^"]+)"', chunk) \
                or re.search(r'<img[^>]+src="([^"]+)"', chunk)
            image = localize_image(img_m.group(1), "product") if img_m else ""

            # 详情链接
            link_m = re.search(r'href="([^"]*?/tcg/product/[^"]*?\.html)"', chunk)
            detail_url = to_abs(link_m.group(1)) if link_m else ""

            # 属性键值对：发售日期 / 建议零售价 / 商品内容 / 购买渠道
            fields = {}
            for fm in re.finditer(
                r'<span class="Description_title">(.*?)</span>\s*'
                r'<span class="Description_body">(.*?)</span>', chunk, re.S):
                k = clean(fm.group(1))
                v = clean(fm.group(2))
                if k:
                    fields[k] = v

            release_raw = fields.get("发售日期", "")
            date_str, ts = parse_cn_date(release_raw)

            content = fields.get("商品内容", "")
            # 商品内容里随附的周边（冰箱贴 / 徽章 / 磁吸贴 等）单独打标签，方便检索
            bundled = [k for k in BUNDLED_GOODS_KW if k in content]

            out.append({
                "name": title,
                "category": cn_name,
                "release_raw": release_raw,
                "release_date": date_str,
                "release_ts": ts,
                "price": fields.get("建议零售价", ""),
                "content": content,
                "channel": fields.get("购买渠道", ""),
                "bundled": bundled,
                "image": image,
                "url": detail_url,
            })
    return out


# ----------------------------------------------------------------------------
# 1b. 周边商品资讯（衣服饰品 / 生活杂货 / 玩具玩偶 / 文具 / 食品 / 其他）
# ----------------------------------------------------------------------------
GOODS_RE = re.compile(
    r'<li class="card__element[^"]*">\s*'
    r'<a href="([^"]+)">.*?'
    r'<img src="([^"]*)"[^>]*>\s*</figure>.*?'
    r"<p>(.*?)</p>.*?"
    r'card__footer--date">(.*?)</time>',
    re.S,
)


def fetch_goods_news(pages=GOODS_PAGES):
    """抓取官网「商品」频道的周边新品资讯（含冰箱贴、徽章、毛绒等）。"""
    out, seen = [], set()
    # 先抓子分类（分类标签更精确），最后抓「全部」补漏
    targets = GOODS_CATS + [("", "周边新品")]
    for slug, cn in targets:
        for p in range(1, pages + 1):
            base = URL_GOODS if not slug else f"{URL_GOODS}/{slug}"
            url = base if p == 1 else f"{base}/p/{p}"
            page = get(url)
            if not page:
                break
            found = 0
            for link, img, title, date in GOODS_RE.findall(page):
                link = to_abs(link)
                if not link or link in seen:
                    continue
                seen.add(link)
                found += 1
                ds, ts = parse_cn_date(clean(date))
                out.append({
                    "title": clean(title),
                    "url": link,
                    "image": localize_image(img, "card"),
                    "date": ds or clean(date),
                    "date_ts": ts,
                    "category": cn,
                })
            if found == 0:
                break
            time.sleep(0.4)

    # 周边资讯更新很慢，只保留近 12 个月内的，避免栏目里堆满陈旧内容
    cutoff = int((datetime.now(CST) - timedelta(days=365)).timestamp())
    out = [x for x in out if x.get("date_ts", 0) >= cutoff]
    out.sort(key=lambda x: x.get("date_ts", 0), reverse=True)
    return out


# ----------------------------------------------------------------------------
# 2. 卡牌资讯归档（活动 / 赛事、牌店快闪线索、环境牌组线索、赛制公告）
# ----------------------------------------------------------------------------
CARD_RE = re.compile(
    r'<li class="card__element[^"]*">\s*'
    r'<a href="([^"]+)">.*?'
    r'<img src="([^"]*)"[^>]*>\s*</figure>.*?'
    r'<div class="card__products-title">(.*?)</div>.*?'
    r'card__footer--category">(.*?)</time>.*?'
    r'card__footer--date">(.*?)</time>',
    re.S,
)

# 栏目归类关键词
EVENT_KW = ["赛", "报名", "预赛", "正赛", "对战", "挑战赛", "欢庆赛", "杯", "联赛", "锦标赛", "赛事"]
SHOP_KW = ["道馆", "快闪", "店铺", "开业", "门店", "旗舰店", "见面", "购物站", "购物小站"]
DECK_KW = ["卡组", "构筑", "牌组", "环境", "赛制", "标准赛制", "开放赛制", "禁用", "限制", "调整", "特典卡"]
REG_KW = ["赛制", "标准赛制", "开放赛制", "可使用", "轮替", "禁用"]
# 开店类关键词（用于从门店资讯里挑出真正的「新店预告」）
OPEN_KW = ["开业", "与大家见面", "新店", "开店", "正式营业", "亮相"]


def fetch_news(pages=ARCHIVE_PAGES):
    """抓取卡牌资讯归档前 N 页。"""
    items, seen = [], set()
    for p in range(1, pages + 1):
        url = URL_TCG if p == 1 else f"{URL_TCG}/p/{p}"
        page = get(url)
        if not page:
            continue
        found = 0
        for link, img, title, cat, date in CARD_RE.findall(page):
            link = to_abs(link)
            if not link or link in seen:
                continue
            seen.add(link)
            found += 1
            items.append({
                "title": clean(title).replace("\n", ""),
                "url": link,
                "image": localize_image(img, "card"),
                "category_raw": clean(cat),
                "date": clean(date),
            })
        if found == 0:
            break  # 没有新内容，停止翻页
        time.sleep(0.6)
    return items


# ----------------------------------------------------------------------------
# 4b. 官方赛事结果 → 冠军 / 上位卡组（环境牌组栏目核心数据源）
# ----------------------------------------------------------------------------
# 官方在赛事结束后会发布「冠军诞生」「圆满落幕」「结果公布」类公告，
# 部分公告会写明获奖选手与其使用的卡组，例如：
#   北京站 冠军：拾刻.半梦（古剑豹ex卡组）
RESULT_KW = ["冠军", "落幕", "结果", "优胜", "圆满", "战报", "上位", "结束"]

# 写法一（含卡组，最理想）：「北京站 冠军：拾刻.半梦（古剑豹ex卡组）」
RE_DECK = re.compile(
    r"([^\s：:、，。]{2,12}?)\s*(冠军|亚军|季军|4强|8强|优胜)"
    r"[：:]\s*([^\s（(]+)\s*[（(]([^）)]*?卡组)[）)]")

# 写法二：名字在「冠军」之后 —— 「公开组冠军由“小福蛋.筱艾”夺得」
RE_NAME_AFTER = re.compile(
    r"(公开组|少年组|儿童组)?\s*冠军(?:则)?(?:分别)?由\s*"
    r"[“\"']([^”\"']{2,24})[”\"']")

# 写法三：名字在「冠军」之前 —— 「“JHM.Ditto战队”…斩获公开组冠军」
RE_NAME_BEFORE = re.compile(
    r"[“\"']([^”\"']{2,24})[”\"']\s*(?:凭借)?[^。！\n；]{0,25}?"
    r"(?:斩获|夺得|获得|摘得|拿下|荣获)\s*(?:公开组|少年组|儿童组)?冠军")

# 「少年组与儿童组冠军分别由“X”与“Y”获得」这种一对多的写法
RE_NAME_PAIR = re.compile(
    r"(?:少年组|儿童组)[^。！\n]{0,12}?由\s*"
    r"[“\"']([^”\"']{2,24})[”\"']\s*与\s*[“\"']([^”\"']{2,24})[”\"']")


def fetch_event_results(pages=EVENT_PAGES, extra_news=None):
    """翻赛事活动归档，找出官方赛事结果公告并解析其中的卡组构筑。

    extra_news 可传入综合资讯列表，用于补捞不在 event 分类下的结果公告。
    """
    candidates, seen = [], set()

    # 综合资讯里补捞结果类公告
    for n in (extra_news or []):
        if any(k in n.get("title", "") for k in RESULT_KW) and n["url"] not in seen:
            seen.add(n["url"])
            candidates.append({
                "title": n["title"], "url": n["url"],
                "image": n.get("image", ""), "date": n.get("date", ""),
            })

    for p in range(1, pages + 1):
        url = URL_TCG_EVENT if p == 1 else f"{URL_TCG_EVENT}/p/{p}"
        page = get(url)
        if not page:
            continue
        found = 0
        for link, img, title, cat, date in CARD_RE.findall(page):
            link = to_abs(link)
            if not link or link in seen:
                continue
            seen.add(link)
            found += 1
            t = clean(title).replace("\n", "")
            if any(k in t for k in RESULT_KW):
                candidates.append({
                    "title": t, "url": link,
                    "image": localize_image(img, "card"),
                    "date": clean(date),
                })
        if found == 0:
            break
        time.sleep(0.4)

    results = []
    for c in candidates:
        parsed = parse_result_page(c["url"])
        entries = parsed["entries"]
        if not entries:
            continue  # 抓不到任何名次信息的不收录
        has_deck = any(e.get("deck") for e in entries)
        results.append({
            "title": c["title"],
            "url": c["url"],
            "image": c["image"],
            "date": c["date"],
            "event_name": clean_event_name(c["title"]),
            "entries": entries,
            "has_deck": has_deck,
            "snippets": parsed["snippets"],
        })

    results.sort(key=lambda x: x.get("date", ""), reverse=True)
    return results


def clean_event_name(title):
    """把公告标题收敛成赛事名：去掉「冠军诞生！」「圆满落幕」等结果后缀。"""
    name = title
    for suffix in ["冠军诞生！", "冠军诞生!", "圆满落幕", "圆满结束", "结果公布",
                   "精彩落幕", "顺利结束", "圆满收官"]:
        name = name.replace(suffix, "")
    return name.strip("！! 　")


def parse_result_page(url):
    """抓取赛事结果公告正文，提取 名次 / 选手 / 卡组，并保留提到卡组的原句。

    返回 {"entries": [...], "snippets": [...]}：
      entries  —— 名次 / 站点 / 选手 / 卡组
      snippets —— 正文中出现卡组的原句，用于牌组详情页展示「官方原文」
    """
    page = get(url, retries=2)
    if not page:
        return {"entries": [], "snippets": []}

    # 只取正文区，去掉脚本与页脚「最新资讯」列表
    body = page
    for marker in ["最新资讯", "相关资讯", "article-detail__footer"]:
        i = body.find(marker)
        if i > 0:
            body = body[:i]
    body = re.sub(r"<script.*?</script>", "", body, flags=re.S)
    body = re.sub(r"<style.*?</style>", "", body, flags=re.S)
    text = clean(body)

    entries = []

    # 写法一：明确写出卡组
    for site, rank, player, deck in RE_DECK.findall(text):
        entries.append({
            "site": site.strip(),
            "rank": rank,
            "player": player.strip(),
            "deck": deck.replace("卡组", "").strip(),
        })

    if not entries:
        seen_players = set()

        def add(site, player, rank="冠军"):
            player = player.strip()
            if not player or player in seen_players:
                return
            seen_players.add(player)
            entries.append({"site": site or "公开组", "rank": rank,
                            "player": player, "deck": ""})  # 官方未公布卡组

        for group, player in RE_NAME_AFTER.findall(text):
            add(group, player)
        for player in RE_NAME_BEFORE.findall(text):
            add("公开组", player)
        for p1, p2 in RE_NAME_PAIR.findall(text):
            add("少年组", p1)
            add("儿童组", p2)

    # 去重（同一次公告里可能出现相同条目）
    uniq, seen = [], set()
    for e in entries:
        key = (e["site"], e["rank"], e["player"], e["deck"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(e)

    # 提到卡组的原句摘录（供「查看详细牌组信息」时引用官方原文）
    snips = []
    for sent in re.split(r"[。！\n]", text):
        s = sent.strip()
        if "卡组" not in s or not (6 <= len(s) <= 120):
            continue
        if any(k in s for k in ("冠军", "亚军", "季军", "4强", "8强")) and s not in snips:
            snips.append(s)
        if len(snips) >= 8:
            break

    return {"entries": uniq[:30], "snippets": snips}


def analyze_decks(results):
    """汇总赛事结果，统计各卡组的夺冠成绩 → 环境牌组画像。"""
    stat = {}
    for r in results:
        if not r.get("has_deck"):
            continue
        for e in r["entries"]:
            deck = e.get("deck")
            if not deck:
                continue
            item = stat.setdefault(deck, {
                "deck": deck,
                "wins": 0,
                "top": 0,
                "events": [],
                "players": [],
                "quotes": [],
                "last_date": "",
            })
            # 官方公告里提到这套牌组的原句，作为详细信息的「官方原文」
            for s in (r.get("snippets") or []):
                if deck in s and s not in item["quotes"]:
                    item["quotes"].append(s)
            if e["rank"] == "冠军":
                item["wins"] += 1
            else:
                item["top"] += 1
            item["last_date"] = max(item["last_date"], r.get("date", ""))
            ev = {
                "event": r.get("event_name", ""),
                "rank": e["rank"],
                "site": e.get("site", ""),
                "player": e.get("player", ""),
                "date": r.get("date", ""),
                "url": r.get("url", ""),
            }
            if ev not in item["events"]:
                item["events"].append(ev)
            if e.get("player") and e["player"] not in item["players"]:
                item["players"].append(e["player"])

    # 夺冠次数优先，其次上位次数，再按最近夺冠日期
    decks = sorted(stat.values(),
                   key=lambda x: (-(x["wins"] * 10 + x["top"]), x["last_date"]))
    total_wins = sum(d["wins"] for d in decks) or 1
    for d in decks:
        d["share"] = round(d["wins"] * 100 / total_wins, 1)
    return decks


def route_news(items):
    """把资讯分流到 活动/赛事、牌店/快闪、版本/赛制 三大栏目。

    活动 / 赛事栏目遵循两条硬规则：
      1) 不要纯报名通知（「第 N 批报名信息」这类批次公告）；
      2) 不要已经结束的活动（按公告正文里的活动日期判断）。
    """
    events, shops, decks, regs = [], [], [], []

    for it in items:
        cat = (it["category_raw"] or "").lower()
        title = it["title"] or ""

        # 版本 / 赛制：标题命中赛制关键词
        if any(k in title for k in REG_KW):
            regs.append(it)

        # 牌店：标题命中门店关键词
        if any(k in title for k in SHOP_KW):
            shops.append(it)

        # 活动 / 赛事：官方分类为赛事活动，或标题命中赛事关键词
        if cat == "event" or (cat in ("campaign", "other") and any(k in title for k in EVENT_KW)):
            if not is_registration_notice(title):
                events.append(it)

    dedup = lambda arr: list({x["url"]: x for x in arr}.values())  # noqa: E731
    return dedup(events), dedup(shops), dedup(decks), dedup(regs)


def is_registration_notice(title):
    """判断是否为纯报名批次通知（这类信息时效性极强、过期即无用）。"""
    if "报名信息" in title:
        return True
    if "报名" in title and re.search(r"第\s*[一二三四五六七八九十\d]+\s*批", title):
        return True
    if re.search(r"报名(?:结果|抽选|名单)", title):
        return True
    return False


RE_DATE_FULL = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
RE_DATE_SHORT = re.compile(r"(?<![年月日\d])(\d{1,2})\s*月\s*(\d{1,2})\s*日")

# 正文里需要剔除的行：站点导航、页面标题、图注等
JUNK_LINE = re.compile(
    r"^(图\s*\d|Close|集换式卡牌游戏|商品$|影视|游戏$|店铺|图鉴|客户支持|"
    r"The official|宝可梦集换式卡牌游戏$|赛制$|训练家们)")


def article_text(html):
    """抽取公告正文纯文本（去掉脚本、样式与页脚「最新资讯」列表）。"""
    if not html:
        return ""
    page = re.sub(r"<script.*?</script>", "", html, flags=re.S)
    page = re.sub(r"<style.*?</style>", "", page, flags=re.S)
    for marker in ["最新资讯", "相关资讯"]:
        i = page.find(marker)
        if i > 0:
            page = page[:i]
    return clean(page)


# 「能获得什么」相关关键词，自动提炼简介时优先挑这些句子
REWARD_KW = ["可获得", "获得", "奖励", "奖品", "特典", "领取", "赠送",
             "兑换", "积分", "纪念徽章", "闪卡", "抽选"]


def extract_summary(text, title="", max_len=150):
    """从公告正文提炼「活动简介」，优先说明参加后能获得什么。"""
    if not text:
        return ""
    title = (title or "").strip()
    lines = []
    for line in text.split("\n"):
        line = line.strip()
        if not line or len(line) < 10:
            continue
        if JUNK_LINE.match(line) or "official Pokémon Website" in line:
            continue
        if title and (line == title or line.startswith(title)):
            continue          # 正文首行常常重复标题
        lines.append(line)
    if not lines:
        return ""

    # 优先取讲奖励 / 特典卡 / 积分的句子；没有则退回开头几句
    reward = [l for l in lines if any(k in l for k in REWARD_KW)]
    picked = reward[:3] if reward else lines[:3]
    s = re.sub(r"\s+", " ", " ".join(picked)).strip()
    if len(s) > max_len:
        s = s[:max_len].rstrip("，。、；： ") + "…"
    return s


CURATED_SUMMARY_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "event_summaries.json")


def load_curated_summaries():
    """读取人工撰写的活动简介（按公告链接索引），未配置时返回空表。"""
    try:
        with open(CURATED_SUMMARY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {k: v for k, v in data.items() if not k.startswith("_")}
    except (OSError, ValueError):
        return {}


def extract_event_window(url, page_text=None):
    """从公告正文里提取活动日期，返回 (最早开始日, 最晚结束日)，单位为 YYYY-MM-DD。"""
    text = page_text or ""
    if not text:
        page = get(url, retries=2)
        if not page:
            return "", ""
        page = re.sub(r"<script.*?</script>", "", page, flags=re.S)
        page = re.sub(r"<style.*?</style>", "", page, flags=re.S)
        for marker in ["最新资讯", "相关资讯"]:
            i = page.find(marker)
            if i > 0:
                page = page[:i]
        text = clean(page)

    now = datetime.now(CST)
    days = []
    for y, m, d in RE_DATE_FULL.findall(text):
        try:
            days.append(datetime(int(y), int(m), int(d), tzinfo=CST))
        except ValueError:
            pass
    for m, d in RE_DATE_SHORT.findall(text):
        try:
            dt = datetime(now.year, int(m), int(d), tzinfo=CST)
            # 跨年场景：月份比当前月小 6 个月以上，视作明年
            if dt.month - now.month < -6:
                dt = datetime(now.year + 1, int(m), int(d), tzinfo=CST)
            days.append(dt)
        except ValueError:
            pass

    if not days:
        return "", ""
    return min(days).strftime("%Y-%m-%d"), max(days).strftime("%Y-%m-%d")


def filter_live_events(items, max_items=30, curated=None):
    """剔除已经结束的赛事 / 活动，只保留进行中或尚未开始的。

    curated 为人工撰写的简介（按公告链接索引），命中时优先采用。
    """
    today = datetime.now(CST).strftime("%Y-%m-%d")
    out = []
    for it in items[:max_items]:
        # 抓一次正文，日期区间与活动简介共用，避免重复请求
        text = article_text(get(it["url"], retries=2))
        start, end = extract_event_window(it["url"], text)
        it["start_date"] = start
        it["end_date"] = end
        it["summary"] = ((curated or {}).get(it["url"])
                         or extract_summary(text, it.get("title", "")))
        it["status"] = "待定"
        if end:
            if end >= today:
                it["status"] = "进行中" if (start and start <= today) else "即将开始"
            else:
                continue  # 已结束，丢弃
        else:
            # 正文没有明确日期时，退化为按发布日期判断（60 天内保留）
            pub = it.get("date", "")
            if pub and (datetime.now(CST) - datetime.strptime(pub, "%Y-%m-%d")
                        .replace(tzinfo=CST)).days > 60:
                continue
            it["status"] = "近期公告"
        out.append(it)
    return out


# ----------------------------------------------------------------------------
# 3. 官方店铺（牌店 / 快闪）
# ----------------------------------------------------------------------------

def extract_mascot(gym_name):
    """从道馆名中提取吉祥物名称（括号内的字），用于匹配限定商品。

    例如「宝可梦官方卡牌道馆-上海 中山公园（古月鸟）」→「古月鸟」
    """
    m = re.search(r"[（(]([^）)]+)[）)]", gym_name)
    return m.group(1).strip() if m else ""


def fetch_shops(max_pages=10):
    page = get(URL_SHOP)
    if not page:
        return {"gyms": [], "online": [], "popup": None}

    # 官方卡牌道馆列表存在分页，逐页抓取直到无新增
    pages = [page]
    seen_gym_names = set(
        clean(m) for m in re.findall(r'<div class="shop_name">(.*?)</div>', page, re.S))
    for p in range(2, max_pages + 1):
        sub = get(f"{URL_SHOP}/p/{p}")
        if not sub:
            break
        names = [clean(m) for m in re.findall(r'<div class="shop_name">(.*?)</div>', sub, re.S)]
        if not names or all(n in seen_gym_names for n in names):
            break
        seen_gym_names.update(names)
        pages.append(sub)
        time.sleep(0.5)

    # --- 官方卡牌道馆 ---
    gyms = []
    gym_html = "".join(pages)
    for li in gym_html.split('<li class="shop__element">')[1:]:
        name_m = re.search(r'<div class="shop_name">(.*?)</div>', li, re.S)
        if not name_m:
            continue
        img_m = re.search(r'<img src="([^"]+)"', li)
        rows = {}
        for rm in re.finditer(
            r'<div class="content-row-title">(.*?)</div>\s*'
            r'<div class="content-row-content">(.*?)</div>', li, re.S):
            k = clean(rm.group(1)).rstrip("：:")
            v = clean(rm.group(2))
            if k:
                rows[k] = v
        gym_name = clean(name_m.group(1))
        gym = {
            "name": gym_name,
            "image": localize_image(img_m.group(1), "shop") if img_m else "",
            "hours": rows.get("营业时间", ""),
            "closed": rows.get("休息日", ""),
            "address": rows.get("地址", ""),
        }
        # 注入道馆限定商品（按吉祥物名匹配，来源 52poke 百科，人工维护）
        mascot = extract_mascot(gym_name)
        excl = GYM_EXCL_ENTRIES.get(mascot)
        if excl:
            gym["exclusives"] = GYM_COMMON_EXCLUSIVES
            gym["grand_gift"] = excl.get("grand_gift", "")
            gym["grand_gift_note"] = excl.get("gift_note", "")
            gym["opened"] = excl.get("opened", "")
        # 能出现在官网店铺页的，都是已营业的道馆
        gym["not_yet_open"] = False
        gyms.append(gym)

    # --- 线上官方渠道 ---
    online = []
    for div in page.split('<div class="offical-shop-list-item">')[1:]:
        nm = re.search(r'<div class="offical-shop-list-item-name">(.*?)</div>', div, re.S)
        lk = re.search(r'<a[^>]+href="([^"]+)"', div)
        ig = re.search(r'<img class="offical-shop-list-item-image"[^>]+src="([^"]+)"', div)
        if nm:
            online.append({
                "name": clean(nm.group(1)),
                "url": lk.group(1) if lk else "",
                "image": localize_image(ig.group(1), "shop") if ig else "",
            })

    # --- 官方快闪店横幅 ---
    popup = None
    pm = re.search(r'<section class="popup-shop-section">(.*?)</section>', page, re.S)
    if pm:
        seg = pm.group(1)
        lk = re.search(r'href="([^"]+)"', seg)
        ig = re.search(r'<img src="([^"]+)"', seg)
        popup = {
            "title": "官方快闪店",
            "url": lk.group(1) if lk else "",
            "image": localize_image(ig.group(1), "card") if ig else "",
        }

    # --- 底稿一致性自检 ---------------------------------------------------
    # 官网店铺页只收录「已营业」的道馆，因此凡出现在本列表的道馆，
    # 其人工底稿 gym_exclusives.json 里的 opened 必须是具体日期。
    # 若仍是「计划/预计/尚未」等占位值，说明底稿过期；若根本没有条目，
    # 说明新道馆漏登。两种情况都会静默上线出问题，这里主动告警。
    _date_re = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    _stale, _missing = [], []
    for g in gyms:
        _mascot = extract_mascot(g["name"])
        if _mascot not in GYM_EXCL_ENTRIES:
            _missing.append(g["name"])
        elif not _date_re.match(str(g.get("opened", ""))):
            _stale.append((g["name"], g.get("opened", "") or "空"))
    if _stale:
        print("  [STALE-DRAFT] 以下道馆已出现在官网店铺页（即已开业），但 "
              "gym_exclusives.json 的开业日期不是具体日期（疑似占位/过期），请人工更新：")
        for _nm, _op in _stale:
            print(f"      - {_nm}（opened = {_op}）")
    if _missing:
        print("  [DRAFT-MISSING] 以下道馆已出现在官网店铺页，但 gym_exclusives.json "
              "尚未收录（开业日期/开业特典缺失），请人工补充：")
        for _nm in _missing:
            print(f"      - {_nm}")

    # 反向自检：底稿标着「尚未开业」（not_yet_open），但官网店铺页已收录它，
    # 说明该标记已过期（店已开业），页面会一直标注「尚未开业」造成误导。
    _open_mascots = {extract_mascot(g["name"]) for g in gyms}
    _flag = [(v.get("gym", ""), m) for m, v in GYM_EXCL_ENTRIES.items()
             if v.get("not_yet_open") and m in _open_mascots]
    if _flag:
        print("  [STALE-FLAG] 以下道馆在 gym_exclusives.json 中仍标记 not_yet_open"
              "（尚未开业），但已出现在官网店铺页（即已开业），请人工把该标记改为 false：")
        for _gym, _m in _flag:
            print(f"      - {_gym}（{_m}）")

    return {"gyms": gyms, "online": online, "popup": popup}


def build_upcoming_gyms(open_gyms, news_items):
    """按底稿补齐「已公布开业日期、但尚未开业」的道馆。

    官网店铺页只收录已营业的道馆，因此这类道馆（如 2026-10-13 开业的武汉 江汉）
    不会出现在抓取结果里。这里依据人工底稿 gym_exclusives.json 中
    not_yet_open = true 的条目补进列表，并保留 not_yet_open 标记供页面标注
    「尚未开业」。条目一旦出现在官网店铺页，就不再补（以官网数据为准）。
    """
    open_mascots = {extract_mascot(g["name"]) for g in open_gyms}
    soon = []
    for mascot, excl in GYM_EXCL_ENTRIES.items():
        if not excl.get("not_yet_open") or mascot in open_mascots:
            continue
        city = (excl.get("gym") or "").split()[0] if excl.get("gym") else ""
        # 官网店铺页还没有它，图片先借用「即将开店」公告里的配图（已本地化）
        img = ""
        for n in news_items or []:
            t = n.get("title", "")
            if mascot in t or (city and city in t):
                img = n.get("image", "")
                break
        soon.append({
            "name": f"宝可梦官方卡牌道馆-{excl.get('gym', '')}（{mascot}）",
            "image": img,
            "hours": excl.get("hours", ""),
            "closed": "以设施的休息日为准",
            "address": excl.get("address", ""),
            "exclusives": GYM_COMMON_EXCLUSIVES,
            "grand_gift": excl.get("grand_gift", ""),
            "grand_gift_note": excl.get("gift_note", ""),
            "opened": excl.get("opened", ""),
            "not_yet_open": True,
        })
    return soon


# ----------------------------------------------------------------------------
# 4. 赛制（版本 / 赛制）
# ----------------------------------------------------------------------------
def fetch_regulation():
    page = get(URL_REGULATION)
    if not page:
        return {}

    main = page
    result = {"source_url": URL_REGULATION, "updated_at": "", "standard": {}, "open": {}}

    # 更新日期
    um = re.search(r"更新日期[：:]\s*(\d{4}年\d{1,2}月\d{1,2}日)", clean(page))
    if um:
        ds, _ = parse_cn_date(um.group(1))
        result["updated_at"] = ds or um.group(1)

    # 切成标准赛制 / 开放赛制两段
    i_std = main.find("标准赛制")
    i_open = main.find("开放赛制")
    seg_std = main[i_std:i_open] if i_std >= 0 and i_open > i_std else ""
    seg_open = main[i_open:] if i_open >= 0 else ""

    def parse_seg(seg):
        if not seg:
            return {}
        text = clean(seg)

        # 生效起始日
        eff = ""
        em = re.search(r"[（(]自\s*(\d{4}年\d{1,2}月\d{1,2}日)\s*起[）)]", text)
        if em:
            eff, _ = parse_cn_date(em.group(1))

        # 可用赛制标记：形如 "赛制标记为 G、H、I 、J的卡牌"
        marks = []
        mm = re.search(r"赛制标记为\s*([A-Za-z、\s和]+?)\s*的卡牌", text)
        if mm:
            marks = re.findall(r"\b([A-Za-z])\b", mm.group(1))

        # 可用系列（开放赛制）：形如 “朱&紫”系列的卡牌
        series = [clean(x) for x in re.findall(r"“([^”]+)”系列的卡牌", text)]
        # 禁止卡牌
        banned = []
        bm = re.search(r"以下卡牌无法加入卡组中(.*?)(?:关于过去|※|$)", text, re.S)
        if bm:
            banned = [x for x in (l.strip() for l in bm.group(1).split("\n")) if x][:20]

        # 按 h4 小标题切分区块
        blocks = re.split(r"<h4[^>]*>(.*?)</h4>", seg, flags=re.S)
        sections = []
        for i in range(1, len(blocks), 2):
            title = clean(blocks[i])
            body = blocks[i + 1]
            if not title:
                continue
            texts = [x for x in (clean(x) for x in re.findall(r"<p[^>]*>(.*?)</p>", body, re.S)) if x]
            cards = [x for x in (clean(x) for x in re.findall(r"<li[^>]*>(.*?)</li>", body, re.S)) if x]
            sections.append({"title": title, "texts": texts, "cards": cards})

        return {
            "effective_from": eff,
            "marks": marks,
            "series": series,
            "banned": banned,
            "sections": sections,
            "raw": text[:4000],
        }

    result["standard"] = parse_seg(seg_std)
    result["open"] = parse_seg(seg_open)
    return result


# ----------------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------------
def build():
    print("[1/4] 抓取商品一览 ...")
    products = fetch_products()
    print(f"      -> {len(products)} 条商品")

    print("[2/6] 抓取卡牌资讯 ...")
    news = fetch_news()
    events_raw, shops_news, decks_news, regs = route_news(news)

    print("[3/6] 过滤已结束的赛事活动 ...")
    curated = load_curated_summaries()
    events = filter_live_events(events_raw, curated=curated)
    # 开店动态：只保留「即将开业 / 即将与大家见面」的新店预告，
    # 已开业的不展示，也不是开店的（道馆杯、挑战赛等）一律排除
    soon_open = [n for n in shops_news
                 if "即将" in n["title"] and any(k in n["title"] for k in OPEN_KW)]
    # 赛制调整公告只展示最新的一条，不再堆砌已被新公告取代的历史内容
    regs_latest = sorted(regs, key=lambda x: x.get("date", ""), reverse=True)[:1]
    print(f"      -> 资讯 {len(news)} 条 | 进行中赛事活动 {len(events)}（原 {len(events_raw)}）"
          f" | 即将开店 {len(soon_open)} | 赛制公告 {len(regs)}（取最新 {len(regs_latest)} 条）")

    print("[4/6] 抓取官方赛事结果（冠军卡组）...")
    results = fetch_event_results(extra_news=news)
    decks = analyze_decks(results)
    with_deck = sum(1 for r in results if r["has_deck"])
    print(f"      -> 赛事结果公告 {len(results)} 条（含卡组 {with_deck} 条）"
          f" | 统计到卡组 {len(decks)} 套")

    print("[5/6] 抓取官方店铺 ...")
    shops = fetch_shops()
    open_gyms = shops["gyms"]
    # 尚未开业（官方已公布开业日期）的道馆：官网店铺页不收录，按人工底稿补齐，
    # 排在列表最前，页面会照常显示具体开业日期并标注「尚未开业」
    soon_gyms = build_upcoming_gyms(open_gyms, soon_open)
    gyms_all = soon_gyms + open_gyms
    print(f"      -> 官方卡牌道馆 {len(open_gyms)} 家（已营业）"
          + (f" | 尚未开业 {len(soon_gyms)} 家：" +
             "、".join(g["name"] for g in soon_gyms) if soon_gyms else ""))

    print("[6/6] 抓取周边新品与赛制说明 ...")
    goods_news = fetch_goods_news()
    regulation = fetch_regulation()
    print(f"      -> 周边新品 {len(goods_news)} 条 | 标准赛制标记 "
          f"{regulation.get('standard', {}).get('marks')} | 更新日期 {regulation.get('updated_at')}")

    # 商品按发售日期倒序
    products.sort(key=lambda x: (x["release_ts"] or 0), reverse=True)

    now = datetime.now(CST)
    today = now.strftime("%Y-%m-%d")
    # 新品 / 上新只看近 3 个月：发售日期在今天及之后 = 即将发售（尚未发布）；
    # 在近 3 个月内发售 = 已发售（折叠收纳）；更早发售的不再算「上新」，直接剔除。
    cutoff_ts = int((now - timedelta(days=RECENT_DAYS)).timestamp())
    recent = []
    for p in products:
        rd = p.get("release_date") or ""
        if rd and rd >= today:
            p["release_status"] = "upcoming"
        elif p.get("release_ts", 0) >= cutoff_ts:
            p["release_status"] = "released"
        else:
            continue  # 发售已超过 3 个月，不属于「上新」
        recent.append(p)
    products = recent
    print(f"      -> 近 {RECENT_DAYS} 天内商品 {len(products)} 件"
          f"（未发售 {len([p for p in products if p['release_status'] == 'upcoming'])} 件）")
    data = {
        "meta": {
            "generated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
            "generated_date": now.strftime("%Y-%m-%d"),
            "timezone": "Asia/Shanghai",
            "sources": [
                {"name": "宝可梦中国官方网站 · 商品一览", "url": URL_PRODUCTS},
                {"name": "宝可梦中国官方网站 · 集换式卡牌游戏", "url": URL_TCG},
                {"name": "宝可梦中国官方网站 · 店铺", "url": URL_SHOP},
                {"name": "宝可梦中国官方网站 · 赛制", "url": URL_REGULATION},
            ],
        },
        "products": products,
        "goods_news": goods_news,
        "product_news": [n for n in news if (n["category_raw"] or "").lower() == "product"],
        "events": events,
        "shops": {
            "gyms": gyms_all,      # 含「尚未开业」的预开业道馆（not_yet_open = true）
            "news": soon_open,     # 仅「即将开店」预告
        },
        "decks": {
            # 环境牌组：以 AREAZERO.GG 卡组统计（基于官方完赛排名与参赛人数
            # 换算的表现分）为主，叠加人工撰写的潜力分析。见 META_ANALYSIS。
            "analysis": META_ANALYSIS,
            "results": results,    # 官方赛事结果公告（数据保留，页面不再展示）
            "meta": decks,         # 由官方赛后公告统计出的冠军卡组
            "news": decks_news,    # 官方环境 / 卡组公告
        },
        "regulation": {
            "source_url": URL_REGULATION,
            "updated_at": regulation.get("updated_at", ""),
            "standard": regulation.get("standard", {}),
            "open": regulation.get("open", {}),
            "news": regs_latest,
        },
    }
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=os.path.join(os.path.dirname(__file__), "..", "data"))
    ap.add_argument("--img-dir", default=os.path.join(os.path.dirname(__file__), "..", "assets", "img"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-image", action="store_true", help="跳过图片下载")
    args = ap.parse_args()

    global SKIP_IMAGE, IMG_DIR
    SKIP_IMAGE = args.no_image
    IMG_DIR = os.path.abspath(args.img_dir)
    if not SKIP_IMAGE:
        os.makedirs(IMG_DIR, exist_ok=True)
        if not ensure_pillow():
            print("[!] 未安装 Pillow，跳过图片下载（pip install pillow）", file=sys.stderr)
            SKIP_IMAGE = True

    data = build()

    if args.dry_run:
        print(json.dumps(data, ensure_ascii=False, indent=2)[:3000])
        return

    out_dir = os.path.abspath(args.out_dir)
    os.makedirs(out_dir, exist_ok=True)

    json_path = os.path.join(out_dir, "data.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n已写入 {json_path}")

    js_path = os.path.join(out_dir, "data.js")
    with open(js_path, "w", encoding="utf-8") as f:
        f.write("window.PB_DATA = ")
        json.dump(data, f, ensure_ascii=False)
        f.write(";\n")
    print(f"已写入 {js_path}")

    # 健康检查：关键栏目不能为空
    ok = True
    checks = [
        ("商品", len(data["products"])),
        ("赛事活动", len(data["events"])),
        ("官方道馆", len(data["shops"]["gyms"])),
        ("赛制标记", len(data["regulation"]["standard"].get("marks", []))),
    ]
    for name, n in checks:
        flag = "OK " if n > 0 else "FAIL"
        if n == 0:
            ok = False
        print(f"  [{flag}] {name}: {n}")
    prune_images(IMG_DIR, IMG_KEEP_DAYS)

    if not ok:
        print("\n[!] 部分栏目抓取为空，保留上一次数据更安全。", file=sys.stderr)
        sys.exit(1)


def prune_images(img_dir, keep_days):
    """清理长期未被刷新的图片（对应商品/资讯已下架）。"""
    if not img_dir or not os.path.isdir(img_dir):
        return
    now = time.time()
    removed = 0
    for name in os.listdir(img_dir):
        if not name.endswith(".webp"):
            continue
        p = os.path.join(img_dir, name)
        try:
            if now - os.path.getmtime(p) > keep_days * 86400:
                os.remove(p)
                removed += 1
        except OSError:
            pass
    if removed:
        print(f"  已清理 {removed} 张过期图片")


if __name__ == "__main__":
    main()
