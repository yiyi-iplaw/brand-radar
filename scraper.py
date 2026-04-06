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

RSS_SOURCES = [
    {"name": "36氪", "url": "https://36kr.com/feed"},
    {"name": "虎嗅", "url": "https://www.huxiu.com/rss/0.xml"},
    {"name": "钛媒体", "url": "https://www.tmtpost.com/feed"},
    {"name": "爱范儿", "url": "https://www.ifanr.com/feed"},
    {"name": "白鲸出海", "url": "https://www.baijingapp.com/feed"},
    {"name": "界面新闻科技", "url": "https://www.jiemian.com/lists/277.rss"},
    {"name": "PingWest品玩", "url": "https://pingwest.com/feed"},
]

SIGNAL_KEYWORDS = [
    "出海", "融资", "品牌", "全球", "海外", "亿元", "美元", "轮融资",
    "新消费", "跨境", "DTC", "独立站", "亚马逊", "欧美", "北美",
    "东南亚", "日本", "德国", "英国", "国际", "IPO", "上市",
    "Pre-A", "A轮", "B轮", "C轮", "战略融资", "消费", "科技",
    "智能", "新能源", "电动", "户外", "宠物", "美妆", "家居",
]

def fetch_url(url, timeout=20):
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
            desc = re.sub(r"<[^>]+>", "", desc).strip()[:200]
            if title and len(title) > 4:
                articles.append({"title": title, "desc": desc})
    except Exception as e:
        print(f"RSS parse failed {source_name}: {e}")
    return articles

def is_relevant(article):
    text = article["title"] + " " + article.get("desc", "")
    return any(kw in text for kw in SIGNAL_KEYWORDS)

def analyze_with_gemini(articles, source_name):
    if not articles:
        return {"high": [], "mid": [], "watch": [], "titles": []}

    articles_text = "\n".join([
        f"[{i+1}] {a['title']}" + (f" — {a['desc'][:80]}" if a.get("desc") else "")
        for i, a in enumerate(articles[:25])
    ])

    prompt = f"""你是LawMay P.C.律所的品牌情报助手，专注于识别尚未在美国注册商标的崛起中国品牌。

目标客户画像：类似华为早期、比亚迪出海前、张雪机车这样的品牌。在垂直领域有真实用户基础，开始被媒体报道，有出海意图，但知识产权保护尚未系统化。

目标行业：消费电子、户外运动、美妆个护、宠物用品、新能源汽车配件、家居家具、运动健身、摩托车两轮出行。

今日来源"{source_name}"的内容：

{articles_text}

请将识别出的品牌分为三档：

HIGH（高价值）：有明确出海动作或近期融资，品牌已有一定知名度，强烈建议主动联系。
MID（中价值）：有出海意图或品牌意识萌芽，信号较弱但值得跟进。
WATCH（观察池）：提到了品牌名，信号不明确，先记录。

对每个品牌提供：
- brand_cn: 中文品牌名
- brand_en: 英文品牌名（如无则空字符串）
- industry: 所属行业
- signal: 一句话描述信号
- reason: 判断依据（一句话，说明为何归入该档）
- uspto_keyword: USPTO查询关键词（英文）

返回格式（仅JSON）：
{{
  "high": [...],
  "mid": [...],
  "watch": [...],
  "summary": "今日内容总体评价，一到两句话"
}}

无品牌的档位返回空数组[]。必须返回summary字段。"""

    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        resp = requests.post(
            url,
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.2, "maxOutputTokens": 2000}
            },
            timeout=40
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        text = re.sub(r"```json|```", "", text).strip()
        result = json.loads(text)
        result["titles"] = [a["title"] for a in articles[:10]]
        return result
    except Exception as e:
        print(f"Gemini analysis failed for {source_name}: {e}")
        return {"high": [], "mid": [], "watch": [], "summary": f"分析失败：{e}", "titles": [a["title"] for a in articles[:10]]}

def render_brand_card(b, tier):
    keyword = b.get("uspto_keyword") or b.get("brand_en") or b.get("brand_cn", "")
    tess_url = f"https://tmsearch.uspto.gov/search/search-information?searchInput={requests.utils.quote(keyword)}&searchOption=Basic"
    brand_display = b.get("brand_cn", "")
    if b.get("brand_en"):
        brand_display += f"  {b['brand_en']}"

    if tier == "high":
        badge_style = "background:#FCEBEB;color:#A32D2D;"
        badge_text = "高价值"
        border_style = "border:1.5px solid #f0c0c0;"
    elif tier == "mid":
        badge_style = "background:#FAEEDA;color:#854F0B;"
        badge_text = "中价值"
        border_style = "border:1px solid #e8e8e3;"
    else:
        badge_style = "background:#F1EFE8;color:#5F5E5A;"
        badge_text = "观察池"
        border_style = "border:1px solid #eeeee8;"

    reason_html = f'<p style="font-size:12px;color:#aaa;margin:4px 0 8px;font-style:italic;">{b.get("reason","")}</p>' if b.get("reason") else ""

    return f"""<div style="{border_style}border-radius:10px;padding:14px;margin-bottom:8px;">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:6px;gap:8px;">
    <span style="font-size:15px;font-weight:500;color:#1a1a18;">{brand_display}</span>
    <div style="display:flex;gap:6px;flex-shrink:0;">
      <span style="font-size:11px;{badge_style}padding:2px 8px;border-radius:20px;">{badge_text}</span>
      <span style="font-size:11px;background:#EAF3DE;color:#3B6D11;padding:2px 8px;border-radius:20px;">{b.get("industry","")}</span>
    </div>
  </div>
  <p style="font-size:13px;color:#555;margin:0 0 4px;line-height:1.5;">{b.get("signal","")}</p>
  {reason_html}
  <a href="{tess_url}" style="font-size:12px;color:#185FA5;text-decoration:none;">USPTO TESS 验证 →</a>
</div>"""

def build_report_html(source_results, date_str):
    all_high, all_mid, all_watch = [], [], []
    source_sections = ""

    for sr in source_results:
        result = sr["result"]
        all_high.extend(result.get("high", []))
        all_mid.extend(result.get("mid", []))
        all_watch.extend(result.get("watch", []))

        titles_html = ""
        if result.get("titles"):
            titles_list = "".join([f'<li style="margin-bottom:3px;">{t}</li>' for t in result["titles"]])
            titles_html = f'<ul style="font-size:12px;color:#888;margin:6px 0 0;padding-left:16px;line-height:1.6;">{titles_list}</ul>'

        summary = result.get("summary", "")
        source_sections += f"""<div style="margin-bottom:12px;padding:12px;background:#fafaf8;border-radius:8px;">
  <div style="font-size:13px;font-weight:500;color:#444;margin-bottom:4px;">{sr["name"]} · {sr["count"]} 条相关内容</div>
  <div style="font-size:12px;color:#888;">{summary}</div>
  {titles_html}
</div>"""

    def dedup(lst):
        seen = set()
        out = []
        for b in lst:
            key = (b.get("brand_en","") + b.get("brand_cn","")).lower().strip()
            if key and key not in seen:
                seen.add(key)
                out.append(b)
        return out

    all_high = dedup(all_high)
    all_mid = dedup(all_mid)
    all_watch = dedup(all_watch)
    total = len(all_high) + len(all_mid) + len(all_watch)

    high_html = "".join([render_brand_card(b, "high") for b in all_high]) or '<p style="font-size:13px;color:#ccc;">今日无高价值品牌</p>'
    mid_html = "".join([render_brand_card(b, "mid") for b in all_mid]) or '<p style="font-size:13px;color:#ccc;">今日无中价值品牌</p>'
    watch_html = "".join([render_brand_card(b, "watch") for b in all_watch]) or '<p style="font-size:13px;color:#ccc;">今日无观察池品牌</p>'

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Brand Radar {date_str}</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Segoe UI',sans-serif;background:#f0efe9;padding:24px 16px;margin:0;}}
.card{{max-width:640px;margin:0 auto;background:#fff;border-radius:16px;padding:28px;border:1px solid #e5e5e0;}}
h2{{font-size:14px;font-weight:500;color:#1a1a18;margin:20px 0 10px;padding-bottom:6px;border-bottom:1px solid #f0efe9;}}
</style>
</head>
<body>
<div class="card">
  <div style="margin-bottom:20px;">
    <h1 style="font-size:19px;font-weight:600;color:#1a1a18;margin:0 0 4px;">Brand Radar 每日报告</h1>
    <p style="font-size:13px;color:#aaa;margin:0;">{date_str}</p>
  </div>

  <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-bottom:24px;">
    <div style="background:#FCEBEB;border-radius:8px;padding:12px;">
      <div style="font-size:22px;font-weight:600;color:#A32D2D;">{len(all_high)}</div>
      <div style="font-size:11px;color:#A32D2D;margin-top:2px;">高价值</div>
    </div>
    <div style="background:#FAEEDA;border-radius:8px;padding:12px;">
      <div style="font-size:22px;font-weight:600;color:#854F0B;">{len(all_mid)}</div>
      <div style="font-size:11px;color:#854F0B;margin-top:2px;">中价值</div>
    </div>
    <div style="background:#F1EFE8;border-radius:8px;padding:12px;">
      <div style="font-size:22px;font-weight:600;color:#5F5E5A;">{len(all_watch)}</div>
      <div style="font-size:11px;color:#5F5E5A;margin-top:2px;">观察池</div>
    </div>
  </div>

  <h2>高价值品牌</h2>
  {high_html}

  <h2>中价值品牌</h2>
  {mid_html}

  <h2>观察池</h2>
  {watch_html}

  <h2>数据来源详情</h2>
  {source_sections}

  <hr style="border:none;border-top:1px solid #f0efe9;margin:20px 0 12px;">
  <p style="font-size:11px;color:#c8c8c0;margin:0;">由 Brand Radar 自动生成 · LawMay P.C. · 仅供内部参考</p>
</div>
</body>
</html>"""

def main():
    print(f"Brand Radar starting: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    source_results = []

    for source in RSS_SOURCES:
        print(f"Fetching: {source['name']}")
        content = fetch_url(source["url"])
        if not content:
            source_results.append({"name": source["name"], "count": 0, "result": {"high":[],"mid":[],"watch":[],"summary":"抓取失败","titles":[]}})
            continue
        articles = parse_rss(content, source["name"])
        relevant = [a for a in articles if is_relevant(a)]
        print(f"  {source['name']}: {len(articles)} total, {len(relevant)} relevant")
        result = analyze_with_gemini(relevant, source["name"])
        h = len(result.get("high",[]))
        m = len(result.get("mid",[]))
        w = len(result.get("watch",[]))
        print(f"  high={h} mid={m} watch={w}")
        source_results.append({"name": source["name"], "count": len(relevant), "result": result})

    date_str = datetime.now().strftime("%Y年%m月%d日")
    html = build_report_html(source_results, date_str)
    with open("report.html", "w", encoding="utf-8") as f:
        f.write(html)
    total_high = sum(len(sr["result"].get("high",[])) for sr in source_results)
    total_mid = sum(len(sr["result"].get("mid",[])) for sr in source_results)
    total_watch = sum(len(sr["result"].get("watch",[])) for sr in source_results)
    print(f"Done. High={total_high} Mid={total_mid} Watch={total_watch}")

if __name__ == "__main__":
    main()
