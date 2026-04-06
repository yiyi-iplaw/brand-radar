import requests
import json
import os
import re
from datetime import datetime
from xml.etree import ElementTree as ET

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/rss+xml, application/xml, text/xml, */*"
}

# RSS sources - public feeds, no anti-scraping
RSS_SOURCES = [
    {"name": "36氪", "url": "https://36kr.com/feed"},
    {"name": "虎嗅", "url": "https://www.huxiu.com/rss/0.xml"},
    {"name": "钛媒体", "url": "https://www.tmtpost.com/feed"},
    {"name": "品玩", "url": "https://www.pingwest.com/feed"},
    {"name": "爱范儿", "url": "https://www.ifanr.com/feed"},
    {"name": "白鲸出海", "url": "https://www.baijingapp.com/feed"},
    {"name": "出海头条", "url": "https://chuhaitt.com/feed"},
    {"name": "界面新闻", "url": "https://www.jiemian.com/feed.xml"},
]

# Public HTML pages - exhibition and association directories
HTML_SOURCES = [
    {
        "name": "广交会参展商",
        "url": "https://www.cantonfair.org.cn/en-US/exhibitor/search",
        "type": "html"
    },
    {
        "name": "IT桔子融资",
        "url": "https://www.itjuzi.com/investevent",
        "type": "html"
    },
    {
        "name": "白鲸出海品牌榜",
        "url": "https://www.baijingapp.com/brand",
        "type": "html"
    },
]

# Industry keywords for filtering
INDUSTRY_KEYWORDS = {
    "消费电子": ["耳机", "充电", "摄影", "相机", "手机", "电子", "蓝牙", "智能", "数码", "TWS", "speaker"],
    "户外运动": ["户外", "登山", "露营", "徒步", "骑行", "越野", "背包", "帐篷", "冲锋衣"],
    "美妆个护": ["美妆", "护肤", "彩妆", "化妆", "香水", "美容", "护发", "洗护"],
    "宠物用品": ["宠物", "猫粮", "狗粮", "宠物食品", "宠物用品", "猫咪", "狗狗"],
    "新能源汽车": ["新能源", "电动车", "电动汽车", "充电桩", "车载", "汽车配件", "造车"],
    "家居家具": ["家居", "家具", "收纳", "厨具", "床品", "灯具", "装修"],
    "运动健身": ["健身", "运动", "瑜伽", "跑步", "训练", "器械", "体育"],
    "摩托车两轮": ["摩托", "机车", "电动", "两轮", "踏板", "摩托车", "骑手"],
}

# Brand/overseas signals
SIGNAL_KEYWORDS = [
    "出海", "融资", "品牌", "全球", "海外", "亿元", "美元", "轮融资",
    "新消费", "跨境", "DTC", "独立站", "亚马逊", "沃尔玛", "欧美",
    "北美", "东南亚", "日本", "德国", "英国", "法国", "国际",
    "IPO", "上市", "战略融资", "Pre-A", "A轮", "B轮", "C轮",
]

def fetch_url(url, timeout=15):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"Fetch failed: {url} - {e}")
        return None

def parse_rss(xml_text, source_name):
    articles = []
    try:
        root = ET.fromstring(xml_text)
        items = root.findall(".//item")
        if not items:
            items = root.findall(".//{http://www.w3.org/2005/Atom}entry")
        for item in items[:40]:
            title = (item.findtext("title") or
                     item.findtext("{http://www.w3.org/2005/Atom}title") or "")
            desc = (item.findtext("description") or
                    item.findtext("{http://www.w3.org/2005/Atom}summary") or "")
            title = re.sub(r"<[^>]+>", "", title).strip()
            desc = re.sub(r"<[^>]+>", "", desc).strip()[:300]
            if title and len(title) > 4:
                articles.append({"title": title, "desc": desc})
    except Exception as e:
        print(f"RSS parse failed {source_name}: {e}")
    return articles

def parse_html_generic(html):
    articles = []
    try:
        # Extract text from common content tags
        patterns = [
            r'<h[1-4][^>]*>([^<]{5,100})</h[1-4]>',
            r'<a[^>]*title="([^"]{5,100})"',
            r'"title"\s*:\s*"([^"]{5,100})"',
        ]
        seen = set()
        for pattern in patterns:
            for match in re.findall(pattern, html):
                text = re.sub(r"<[^>]+>", "", match).strip()
                if text and text not in seen:
                    seen.add(text)
                    articles.append({"title": text, "desc": ""})
        return articles[:40]
    except Exception as e:
        print(f"HTML parse failed: {e}")
        return []

def is_relevant(article):
    text = article["title"] + " " + article.get("desc", "")
    has_signal = any(kw in text for kw in SIGNAL_KEYWORDS)
    has_industry = any(
        any(kw in text for kw in kws)
        for kws in INDUSTRY_KEYWORDS.values()
    )
    return has_signal or has_industry

def analyze_with_gemini(articles, source_name):
    if not articles:
        return []

    articles_text = "\n".join([
        f"- {a['title']}" + (f"：{a['desc'][:100]}" if a.get("desc") else "")
        for a in articles[:25]
    ])

    industry_list = "、".join(INDUSTRY_KEYWORDS.keys())

    prompt = f"""你是LawMay P.C.律所的品牌情报助手，专注于识别尚未在美国注册商标的崛起中国品牌。

目标行业：{industry_list}

今日来源"{source_name}"的内容：

{articles_text}

筛选标准：
1. 有真实品牌名称（不是纯代工厂）
2. 有出海意图或已开始出海
3. 有融资或快速增长信号
4. 处于早期到中期阶段（类似华为、比亚迪、张雪机车出海前的状态）
5. 知识产权保护体系尚未完善

对每个品牌提供：
- brand_cn: 中文品牌名
- brand_en: 英文品牌名（如有，否则留空）
- industry: 所属行业
- signal: 一句话描述出海或融资信号
- uspto_keyword: USPTO查询关键词（英文）

返回格式（仅JSON，无其他文字）：
[{{"brand_cn":"","brand_en":"","industry":"","signal":"","uspto_keyword":""}}]

无符合品牌则返回[]。"""

    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        resp = requests.post(
            url,
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1500}
            },
            timeout=30
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        text = re.sub(r"```json|```", "", text).strip()
        result = json.loads(text)
        return result if isinstance(result, list) else []
    except Exception as e:
        print(f"Gemini analysis failed for {source_name}: {e}")
        return []

def build_report_html(all_brands, date_str, source_stats):
    if not all_brands:
        brands_html = """<div style="padding:24px;text-align:center;color:#aaa;font-size:14px;background:#fafafa;border-radius:8px;">
            今日未发现符合条件的品牌
        </div>"""
    else:
        brands_html = ""
        for b in all_brands:
            keyword = b.get("uspto_keyword") or b.get("brand_en") or b.get("brand_cn", "")
            tess_url = f"https://tmsearch.uspto.gov/search/search-information?searchInput={requests.utils.quote(keyword)}&searchOption=Basic"
            brand_display = b.get("brand_cn", "")
            if b.get("brand_en"):
                brand_display += f"  {b['brand_en']}"
            brands_html += f"""<div style="border:1px solid #e8e8e3;border-radius:10px;padding:16px;margin-bottom:10px;">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px;gap:12px;">
    <span style="font-size:15px;font-weight:500;color:#1a1a18;">{brand_display}</span>
    <span style="font-size:11px;background:#EAF3DE;color:#3B6D11;padding:2px 8px;border-radius:20px;white-space:nowrap;flex-shrink:0;">{b.get("industry","")}</span>
  </div>
  <p style="font-size:13px;color:#666;margin:0 0 10px;line-height:1.6;">{b.get("signal","")}</p>
  <a href="{tess_url}" style="font-size:12px;color:#185FA5;text-decoration:none;">USPTO TESS 验证 →</a>
</div>"""

    total_articles = sum(s["count"] for s in source_stats)
    sources_active = sum(1 for s in source_stats if s["count"] > 0)
    stats_rows = "".join([
        f'<tr><td style="padding:3px 8px 3px 0;font-size:12px;color:#888;">{s["name"]}</td><td style="padding:3px 0;font-size:12px;color:#444;">{s["count"]} 条相关内容</td></tr>'
        for s in source_stats
    ])

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Brand Radar {date_str}</title>
<style>
  body{{font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Segoe UI',sans-serif;background:#f0efe9;padding:24px 16px;margin:0;}}
  .card{{max-width:620px;margin:0 auto;background:#fff;border-radius:16px;padding:28px;border:1px solid #e5e5e0;}}
</style>
</head>
<body>
<div class="card">
  <div style="margin-bottom:20px;">
    <h1 style="font-size:19px;font-weight:600;color:#1a1a18;margin:0 0 4px;">Brand Radar 每日报告</h1>
    <p style="font-size:13px;color:#aaa;margin:0;">{date_str}</p>
  </div>

  <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-bottom:24px;">
    <div style="background:#f5f5f2;border-radius:8px;padding:12px;">
      <div style="font-size:22px;font-weight:600;color:#1a1a18;">{len(all_brands)}</div>
      <div style="font-size:11px;color:#888;margin-top:2px;">发现品牌</div>
    </div>
    <div style="background:#f5f5f2;border-radius:8px;padding:12px;">
      <div style="font-size:22px;font-weight:600;color:#1a1a18;">{total_articles}</div>
      <div style="font-size:11px;color:#888;margin-top:2px;">分析文章</div>
    </div>
    <div style="background:#f5f5f2;border-radius:8px;padding:12px;">
      <div style="font-size:22px;font-weight:600;color:#1a1a18;">{sources_active}</div>
      <div style="font-size:11px;color:#888;margin-top:2px;">活跃数据源</div>
    </div>
  </div>

  <h2 style="font-size:14px;font-weight:500;color:#1a1a18;margin:0 0 12px;">今日潜在客户品牌</h2>
  {brands_html}

  <details style="margin-top:20px;">
    <summary style="font-size:12px;color:#aaa;cursor:pointer;">数据来源详情</summary>
    <table style="margin-top:8px;border-collapse:collapse;">{stats_rows}</table>
  </details>

  <hr style="border:none;border-top:1px solid #f0efe9;margin:20px 0 12px;">
  <p style="font-size:11px;color:#c8c8c0;margin:0;">由 Brand Radar 自动生成 · LawMay P.C. · 仅供内部参考</p>
</div>
</body>
</html>"""

def main():
    print(f"Brand Radar starting: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    all_brands = []
    source_stats = []

    # Process RSS sources
    for source in RSS_SOURCES:
        print(f"Fetching RSS: {source['name']}")
        content = fetch_url(source["url"])
        if not content:
            source_stats.append({"name": source["name"], "count": 0})
            continue
        articles = parse_rss(content, source["name"])
        relevant = [a for a in articles if is_relevant(a)]
        print(f"  {source['name']}: {len(articles)} total, {len(relevant)} relevant")
        source_stats.append({"name": source["name"], "count": len(relevant)})
        if relevant:
            brands = analyze_with_gemini(relevant, source["name"])
            print(f"  Found {len(brands)} brands")
            all_brands.extend(brands)

    # Process HTML sources
    for source in HTML_SOURCES:
        print(f"Fetching HTML: {source['name']}")
        content = fetch_url(source["url"])
        if not content:
            source_stats.append({"name": source["name"], "count": 0})
            continue
        articles = parse_html_generic(content)
        relevant = [a for a in articles if is_relevant(a)]
        print(f"  {source['name']}: {len(articles)} total, {len(relevant)} relevant")
        source_stats.append({"name": source["name"], "count": len(relevant)})
        if relevant:
            brands = analyze_with_gemini(relevant, source["name"])
            print(f"  Found {len(brands)} brands")
            all_brands.extend(brands)

    # Deduplicate
    seen = set()
    unique_brands = []
    for b in all_brands:
        key = (b.get("brand_en", "") + b.get("brand_cn", "")).lower().strip()
        if key and key not in seen:
            seen.add(key)
            unique_brands.append(b)

    date_str = datetime.now().strftime("%Y年%m月%d日")
    html = build_report_html(unique_brands, date_str, source_stats)
    with open("report.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Done. Unique brands found: {len(unique_brands)}")

if __name__ == "__main__":
    main()
