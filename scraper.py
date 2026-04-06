import requests
import json
import os
import re
from datetime import datetime
from bs4 import BeautifulSoup

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
EMAIL_TO = os.environ.get("EMAIL_TO")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

SOURCES = [
    {
        "name": "36氪融资快讯",
        "url": "https://36kr.com/information/funding/",
        "type": "36kr"
    },
    {
        "name": "虎嗅出海报道",
        "url": "https://www.huxiu.com/search.html?query=%E5%87%BA%E6%B5%B7%E5%93%81%E7%89%8C",
        "type": "huxiu"
    },
    {
        "name": "钛媒体品牌出海",
        "url": "https://www.tmtpost.com/search?q=%E5%93%81%E7%89%8C%E5%87%BA%E6%B5%B7",
        "type": "tmtpost"
    }
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
        href = item.get("href", "")
        if title and len(title) > 5:
            articles.append({"title": title, "url": href})
    return articles

def extract_articles_generic(html, source_name):
    soup = BeautifulSoup(html, "html.parser")
    articles = []
    for tag in soup.select("h1, h2, h3, h4, a"):
        text = tag.get_text(strip=True)
        if len(text) > 10 and len(text) < 200:
            href = tag.get("href", "") if tag.name == "a" else ""
            articles.append({"title": text, "url": href})
    seen = set()
    unique = []
    for a in articles:
        if a["title"] not in seen:
            seen.add(a["title"])
            unique.append(a)
    return unique[:25]

def analyze_with_claude(articles_text, source_name):
    prompt = f"""你是一名专注于中国品牌出海的知识产权律师助手。

以下是今天从"{source_name}"抓取的文章标题列表：

{articles_text}

请从中识别出：
1. 正在崛起的中国品牌（有自己品牌名称的公司，非纯代工）
2. 有出海信号或融资信号的品牌
3. 处于早期到中期阶段、尚未在全球建立完整知识产权保护体系的品牌

对每个识别出的品牌，请提供：
- 品牌名称（中英文都写出来，如果有）
- 所属行业
- 出海/融资信号简述（一句话）
- USPTO 查询建议关键词

请以 JSON 格式返回，结构如下：
[
  {{
    "brand_cn": "品牌中文名",
    "brand_en": "Brand English Name",
    "industry": "行业",
    "signal": "信号描述",
    "uspto_keyword": "查询关键词"
  }}
]

只返回 JSON，不要其他文字。如果没有找到符合条件的品牌，返回空数组 []。"""

    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 1000,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=30
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["content"][0]["text"]
        text = re.sub(r"```json|```", "", text).strip()
        return json.loads(text)
    except Exception as e:
        print(f"Claude analysis failed: {e}")
        return []

def build_email_html(all_brands, date_str):
    if not all_brands:
        brands_html = "<p style='color:#888;'>今日未发现符合条件的品牌。</p>"
    else:
        brands_html = ""
        for b in all_brands:
            tess_url = f"https://tmsearch.uspto.gov/search/search-information?searchInput={requests.utils.quote(b.get('uspto_keyword', b.get('brand_en', '')))}&searchOption=Basic"
            brands_html += f"""
<div style="border:1px solid #e5e5e0;border-radius:12px;padding:16px;margin-bottom:12px;background:#fff;">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
    <span style="font-size:16px;font-weight:500;color:#1a1a18;">{b.get('brand_cn', '')} &nbsp; {b.get('brand_en', '')}</span>
    <span style="font-size:12px;background:#EAF3DE;color:#3B6D11;padding:3px 10px;border-radius:20px;">{b.get('industry', '')}</span>
  </div>
  <p style="font-size:13px;color:#888;margin:0 0 8px;">{b.get('signal', '')}</p>
  <a href="{tess_url}" style="font-size:13px;color:#185FA5;text-decoration:none;">在 USPTO TESS 验证 →</a>
</div>"""

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>Brand Radar 每日报告</title></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f5f5f3;padding:32px 16px;margin:0;">
  <div style="max-width:600px;margin:0 auto;background:#fff;border-radius:16px;padding:32px;border:1px solid #e5e5e0;">
    <h1 style="font-size:20px;font-weight:500;color:#1a1a18;margin:0 0 4px;">Brand Radar 每日报告</h1>
    <p style="font-size:14px;color:#888;margin:0 0 24px;">{date_str} &nbsp;|&nbsp; 崛起中国品牌监控</p>
    <hr style="border:none;border-top:1px solid #e5e5e0;margin-bottom:24px;">
    <h2 style="font-size:15px;font-weight:500;color:#1a1a18;margin:0 0 16px;">今日发现品牌（{len(all_brands)} 个）</h2>
    {brands_html}
    <hr style="border:none;border-top:1px solid #e5e5e0;margin-top:24px;margin-bottom:16px;">
    <p style="font-size:12px;color:#b4b2a9;margin:0;">由 Brand Radar 自动生成 · LawMay P.C.</p>
  </div>
</body>
</html>"""

def send_email(subject, html_content):
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
    SMTP_USER = os.environ.get("SMTP_USER")
    SMTP_PASS = os.environ.get("SMTP_PASS")

    if not all([SMTP_USER, SMTP_PASS, EMAIL_TO]):
        print("Email config missing, saving report to report.html instead")
        with open("report.html", "w", encoding="utf-8") as f:
            f.write(html_content)
        print("Report saved to report.html")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_USER
    msg["To"] = EMAIL_TO
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, EMAIL_TO, msg.as_string())
    print(f"Email sent to {EMAIL_TO}")

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
        brands = analyze_with_claude(articles_text, source["name"])
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
    subject = f"Brand Radar {date_str} · 发现 {len(unique_brands)} 个潜在客户品牌"
    send_email(subject, html)
    print(f"Done. Total unique brands found: {len(unique_brands)}")

if __name__ == "__main__":
    main()
