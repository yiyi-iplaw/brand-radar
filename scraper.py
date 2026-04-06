import requests
import json
import os
import re
from datetime import datetime
from bs4 import BeautifulSoup

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
EMAIL_TO = os.environ.get("EMAIL_TO")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

SOURCES = [
    {"name": "36氪融资快讯", "url": "https://36kr.com/information/funding/", "type": "36kr"},
    {"name": "虎嗅出海报道", "url": "https://www.huxiu.com/search.html?query=%E5%87%BA%E6%B5%B7%E5%93%81%E7%89%8C", "type": "huxiu"},
    {"name": "钛媒体品牌出海", "url": "https://www.tmtpost.com/search?q=%E5%93%81%E7%89%8C%E5%87%BA%E6%B5%B7", "type": "tmtpost"}
]

def fetch_page(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"Fetch failed: {url} - {e}")
        return None

def extract_articles_36kr(html):
    soup = BeautifulSoup(html, "html.parser")
    articles = []
    items = soup.select("a.article-item-title, a.title, h3 a, h2 a")
    for item in items[:20]:
        title = item.get_text(strip=True)
        if title and len(title) > 5:
            articles.append({"title": title})
    return articles

def extract_articles_generic(html, source_name):
    soup = BeautifulSoup(html, "html.parser")
    articles = []
    for tag in soup.select("h1, h2, h3, h4, a"):
        text = tag.get_text(strip=True)
        if len(text) > 10 and len(text) < 200:
            articles.append({"title": text})
    seen = set()
    unique = []
    for a in articles:
        if a["title"] not in seen:
            seen.add(a["title"])
            unique.append(a)
    return unique[:25]

def analyze_with_gemini(articles_text, source_name):
    prompt = f"""你是一名专注于中国品牌出海的知识产权律师助手。

以下是今天从"{source_name}"抓取的文章标题列表：

{articles_text}

请从中识别出正在崛起的中国品牌，有出海或融资信号，处于早期到中期阶段。

对每个品牌提供：品牌中英文名、行业、出海融资信号简述、USPTO查询关键词。

以JSON格式返回：
[{{"brand_cn":"中文名","brand_en":"English Name","industry":"行业","signal":"信号","uspto_keyword":"关键词"}}]

只返回JSON，无其他文字。无符合品牌返回[]。"""

    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        resp = requests.post(
            url,
            headers={"Content-Type": "application/json"},
            json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.3}},
            timeout=30
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        text = re.sub(r"```json|```", "", text).strip()
        return json.loads(text)
    except Exception as e:
        print(f"Gemini analysis failed: {e}")
        return []

def build_email_html(all_brands, date_str):
    if not all_brands:
        brands_html = "<p style='color:#888;'>今日未发现符合条件的品牌。</p>"
    else:
        brands_html = ""
        for b in all_brands:
            keyword = b.get("uspto_keyword", b.get("brand_en", ""))
            tess_url = f"https://tmsearch.uspto.gov/search/search-information?searchInput={requests.utils.quote(keyword)}&searchOption=Basic"
            brands_html += f"""<div style="border:1px solid #e5e5e0;border-radius:12px;padding:16px;margin-bottom:12px;background:#fff;">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
    <span style="font-size:16px;font-weight:500;color:#1a1a18;">{b.get("brand_cn","")} &nbsp; {b.get("brand_en","")}</span>
    <span style="font-size:12px;background:#EAF3DE;color:#3B6D11;padding:3px 10px;border-radius:20px;">{b.get("industry","")}</span>
  </div>
  <p style="font-size:13px;color:#888;margin:0 0 8px;">{b.get("signal","")}</p>
  <a href="{tess_url}" style="font-size:13px;color:#185FA5;text-decoration:none;">在 USPTO TESS 验证 →</a>
</div>"""

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Brand Radar</title></head>
<body style="font-family:-apple-system,sans-serif;background:#f5f5f3;padding:32px 16px;margin:0;">
  <div style="max-width:600px;margin:0 auto;background:#fff;border-radius:16px;padding:32px;border:1px solid #e5e5e0;">
    <h1 style="font-size:20px;font-weight:500;color:#1a1a18;margin:0 0 4px;">Brand Radar 每日报告</h1>
    <p style="font-size:14px;color:#888;margin:0 0 24px;">{date_str} · 崛起中国品牌监控</p>
    <hr style="border:none;border-top:1px solid #e5e5e0;margin-bottom:24px;">
    <h2 style="font-size:15px;font-weight:500;color:#1a1a18;margin:0 0 16px;">今日发现品牌（{len(all_brands)} 个）</h2>
    {brands_html}
    <hr style="border:none;border-top:1px solid #e5e5e0;margin-top:24px;margin-bottom:16px;">
    <p style="font-size:12px;color:#b4b2a9;margin:0;">由 Brand Radar 自动生成 · LawMay P.C.</p>
  </div>
</body></html>"""

def main():
    print(f"Brand Radar starting: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    all_brands = []

    for source in SOURCES:
        print(f"Fetching: {source['name']}")
        html = fetch_page(source["url"])
        if not html:
            continue
        if source["type"] == "36kr":
            articles = extract_articles_36kr(html)
        else:
            articles = extract_articles_generic(html, source["name"])
        if not articles:
            print(f"No articles found from {source['name']}")
            continue
        articles_text = "\n".join([f"- {a['title']}" for a in articles])
        print(f"Analyzing {len(articles)} articles from {source['name']}...")
        brands = analyze_with_gemini(articles_text, source["name"])
        print(f"Found {len(brands)} brands from {source['name']}")
        all_brands.extend(brands)

    seen = set()
    unique_brands = []
    for b in all_brands:
        key = b.get("brand_en", "") + b.get("brand_cn", "")
        if key and key not in seen:
            seen.add(key)
            unique_brands.append(b)

    date_str = datetime.now().strftime("%Y年%m月%d日")
    html = build_email_html(unique_brands, date_str)
    with open("report.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Report saved. Total unique brands found: {len(unique_brands)}")

if __name__ == "__main__":
    main()
