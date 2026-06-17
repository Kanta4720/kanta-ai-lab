#!/usr/bin/env python
# coding: utf-8

import os
import sys
import json
import re
import difflib
import calendar
import requests
import feedparser
import trafilatura
from openai import OpenAI
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- 設定 --- #

JST = timezone(timedelta(hours=9))

NEWS_API_KEY = os.environ.get("NEWS_API_KEY")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")

client = OpenAI()

# カテゴリ一覧
CATEGORIES = ["Economy", "Markets", "Tech", "World", "Energy"]

# NewsAPI クエリ
NEWSAPI_QUERIES = [
    {"q": "economy recession inflation interest rate",            "category": "Economy"},
    {"q": "stock market S&P500 Nasdaq financial markets",        "category": "Markets"},
    {"q": "artificial intelligence technology innovation",        "category": "Tech"},
    {"q": "geopolitics international relations trade war",        "category": "World"},
    {"q": "oil gas energy renewable climate",                    "category": "Energy"},
]

# RSS フィード（NewsAPI 取得失敗時のフォールバック）
FEEDS = [
    {"source": "Reuters",        "category": "Economy",     "url": "https://feeds.reuters.com/reuters/businessNews"},
    {"source": "BBC Business",   "category": "Economy",     "url": "https://feeds.bbci.co.uk/news/business/rss.xml"},
    {"source": "CNBC",           "category": "Markets",     "url": "https://www.cnbc.com/id/10000664/device/rss/rss.html"},
    {"source": "The Economist",  "category": "Economy",     "url": "https://www.economist.com/business/rss.xml"},
    {"source": "Associated Press","category": "Economy",    "url": "https://apnews.com/hub/business/rss.xml"},
    {"source": "TechCrunch",     "category": "Tech",        "url": "https://techcrunch.com/feed/"},
    {"source": "Wired",          "category": "Tech",        "url": "https://www.wired.com/feed/rss"},
    {"source": "Ars Technica",   "category": "Tech",        "url": "https://feeds.arstechnica.com/arstechnica/index"},
    {"source": "Hacker News",    "category": "Tech",        "url": "https://news.ycombinator.com/rss"},
    {"source": "MarketWatch",    "category": "Markets",     "url": "https://feeds.content.dowjones.io/public/rss/mw_topstories"},
]

ARTICLES_PER_FEED = 3
DEDUP_THRESHOLD = 0.65

# --- 関数定義 --- #

def normalize_title(title):
    return re.sub(r'[^\w\s]', '', title.lower())

def deduplicate(articles):
    seen_urls   = set()
    seen_titles = []
    unique      = []
    for art in articles:
        if art["url"] in seen_urls:
            print(f"[DEDUP] URL重複スキップ: {art['title'][:60]}")
            continue
        seen_urls.add(art["url"])
        norm = normalize_title(art["title"])
        if any(difflib.SequenceMatcher(None, norm, t).ratio() >= DEDUP_THRESHOLD for t in seen_titles):
            print(f"[DEDUP] 類似タイトルスキップ: {art['title'][:60]}")
            continue
        seen_titles.append(norm)
        unique.append(art)
    print(f"[DEDUP] {len(articles)}件 → {len(unique)}件（{len(articles)-len(unique)}件除去）")
    return unique

def fetch_from_newsapi():
    """NewsAPI からニュースを取得する"""
    if not NEWS_API_KEY:
        print("[NewsAPI] NEWS_API_KEY が設定されていません。スキップします。")
        return []

    from_date = (datetime.now(timezone.utc) - timedelta(hours=25)).strftime('%Y-%m-%dT%H:%M:%SZ')
    articles  = []

    for qconf in NEWSAPI_QUERIES:
        try:
            resp = requests.get(
                "https://newsapi.org/v2/everything",
                params={
                    "q":        qconf["q"],
                    "language": "en",
                    "sortBy":   "publishedAt",
                    "from":     from_date,
                    "pageSize": 5,
                    "apiKey":   NEWS_API_KEY,
                },
                timeout=15,
            )
            data = resp.json()
            if data.get("status") != "ok":
                print(f"[NewsAPI] エラー: {data.get('message', 'unknown')}")
                continue

            for art in data.get("articles", []):
                title = art.get("title") or ""
                url   = art.get("url")   or ""
                if not title or not url or url == "https://removed.com":
                    continue

                pub_date = None
                raw_dt = art.get("publishedAt")
                if raw_dt:
                    try:
                        dt = datetime.fromisoformat(raw_dt.replace("Z", "+00:00")).astimezone(JST)
                        pub_date = dt.strftime("%Y-%m-%d %H:%M")
                    except Exception:
                        pass

                desc    = art.get("description") or ""
                content = art.get("content")     or ""
                combined = f"{desc}\n\n{content}".strip()

                articles.append({
                    "title":            title,
                    "url":              url,
                    "source":           art.get("source", {}).get("name", "NewsAPI"),
                    "default_category": qconf["category"],
                    "content":          combined,
                    "published_at":     pub_date,
                })

            print(f"[NewsAPI] '{qconf['q'][:40]}...' → {len(data.get('articles', []))} 件取得")

        except Exception as e:
            print(f"[NewsAPI] クエリ失敗 '{qconf['q'][:40]}': {e}")

    print(f"[NewsAPI] 合計 {len(articles)} 件収集")
    return articles

def fetch_from_rss():
    """RSS フィードから記事を取得する"""
    articles = []
    for feed in FEEDS:
        try:
            d = feedparser.parse(feed["url"])
            for entry in d.entries[:ARTICLES_PER_FEED]:
                pub_date = None
                for attr in ("published_parsed", "updated_parsed"):
                    parsed = getattr(entry, attr, None)
                    if parsed:
                        try:
                            ts     = calendar.timegm(parsed)
                            pub_dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(JST)
                            pub_date = pub_dt.strftime("%Y-%m-%d %H:%M")
                        except Exception:
                            pass
                        break

                content = getattr(entry, "summary", "") or getattr(entry, "description", "") or ""
                articles.append({
                    "title":            entry.title,
                    "url":              entry.link,
                    "source":           feed["source"],
                    "default_category": feed["category"],
                    "content":          content,
                    "published_at":     pub_date,
                })
        except Exception as e:
            print(f"[RSS] フィード取得失敗 {feed['url']}: {e}")
    print(f"[RSS] 合計 {len(articles)} 件収集")
    return articles

def fetch_full_content(url):
    """trafilatura で記事本文を取得する"""
    try:
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            text = trafilatura.extract(downloaded, include_comments=False, include_tables=False, deduplicate=True)
            if text:
                return text
    except Exception:
        pass
    return None

def analyze_with_ai(content, title, default_category):
    """AI で記事を分析・要約する"""
    if not content:
        return None

    prompt = f"""以下の英語ニュース記事を精読し、ビジネスプロフェッショナル向けに詳細な分析レポートをJSON形式で出力してください。

記事タイトル: {title}
記事内容:
{content[:5000]}

《出力要件》
各フィールドは必ず指定された文字数・深度を満たすこと。表面的な言い換えは不可。数字・企業名・日付・固有名詞を積極的に使うこと。

出力形式（JSON形式で返してください）:
{{
  "summary": "【２〜４文】記事の核心を詳しく要約。何が起きたか・いつ・誰が関与しているか・規模や数字・経緯を網羅し、原文を読まなくても全体像が把握できる水準で書く（日本語）",
  "summary_2lines": "【１〜２文】最も重要な点のみを簡潔にまとめたリード文（日本語）",
  "why_it_matters": "【２〜３文】このニュースが重要な理由・業界全体への影響・今後起きうる展開・見落とされがちな論点を専門家視点で解説（日本語）",
  "market_impact": "【１〜２文】市場・経済・投賄家への具体的な影響。定量的・定性的分析（日本語）",
  "category": "Economy / Markets / Tech / World / Energy のいずれか1つ"
}}
"""
    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a senior global markets analyst and financial journalist with 20+ years of experience. "
                        "Your analysis is precise, data-driven, and provides actionable insights. "
                        "Always write in fluent, professional Japanese. Respond in JSON format."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        print(f"[AI] 分析エラー '{title[:50]}': {e}")
        return None

def process_article(raw):
    """1記事を処理してAI分析済みの記事dictを返す"""
    print(f"Processing: {raw['title'][:70]}")
    try:
        content = raw["content"]

        full = fetch_full_content(raw["url"])
        if full and len(full) > len(content):
            content = full

        if not content:
            print(f"  → コンテンツ取得失敗、スキップ")
            return None

        analysis = analyze_with_ai(content, raw["title"], raw["default_category"])
        if not analysis:
            return None

        return {
            "title":          raw["title"],
            "summary":        analysis.get("summary", ""),
            "summary_2lines": analysis.get("summary_2lines", ""),
            "why_it_matters": analysis.get("why_it_matters", ""),
            "market_impact":  analysis.get("market_impact", ""),
            "category":       analysis.get("category", raw["default_category"]),
            "source":         raw["source"],
            "url":            raw["url"],
            "published_at":   raw["published_at"],
        }
    except Exception as e:
        print(f"[処理エラー] '{raw['title'][:50]}': {e}")
        return None

def select_top5(articles):
    """AI で重要記事 TOP5 を選定する"""
    if not articles:
        return []

    listing = [f"{i}: [{a['category']}] {a['title']} — {a.get('summary_2lines', '')[:80]}" for i, a in enumerate(articles)]
    prompt  = f"""以下のニュースから、グローバルなビジネスパーソンにとって最重要な5件を選び、インデックス番号をJSON配列で返してください。
経済・市場・地策リスクを重視してください。

ニュース一覧:
{json.dumps(listing, ensure_ascii=False, indent=2)}

出力形式（JSON）: {{"top5_indices": [番号1, 番号2, 番号3, 番号4, 番号5]}}
"""
    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You are an expert editor for a global business news brief. Respond in JSON format."},
                {"role": "user",   "content": prompt},
            ],
        )
        result  = json.loads(resp.choices[0].message.content)
        indices = result.get("top5_indices", [])
        return [articles[i] for i in indices if i < len(articles)]
    except Exception as e:
        print(f"[TOP5選定エラー] {e}")
        return articles[:5]

# --- メイン処理 --- #

def main():
    # Step 1: ニュース収集（NewsAPI → RSS フォールバック）
    raw_articles = fetch_from_newsapi()
    if len(raw_articles) < 5:
        print(f"[INFO] NewsAPI 取得数が少ないため RSS を補完します")
        raw_articles.extend(fetch_from_rss())

    # Step 2: 重複除去
    unique = deduplicate(raw_articles)

    # Step 3: AI 並列処理
    processed = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(process_article, raw): raw["title"] for raw in unique}
        for future in as_completed(futures):
            try:
                result = future.result()
                if result:
                    processed.append(result)
            except Exception as e:
                print(f"[並列処理エラー] {futures[future][:50]}: {e}")

    if not processed:
        print("ERROR: 記事を1件も取得できませんでした。")
        sys.exit(1)

    print(f"[INFO] 合計 {len(processed)} 件の記事を処理しました。")

    # Step 4: カテゴリ分類
    categories = {cat: [] for cat in CATEGORIES}
    for art in processed:
        if art["category"] in categories:
            categories[art["category"]].append(art)

    # Step 5: TOP5 選定
    todays_brief = select_top5(processed)

    # Step 6: JSON 出力
    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    output = {
        "generated_at_jst": now,
        "todays_brief":     todays_brief,
        "categories":       categories,
    }

    script_dir  = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(os.path.dirname(script_dir), "news.json")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Successfully generated news.json at {output_path}")

if __name__ == "__main__":
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        print("Error: OPENAI_API_KEY environment variable not set or empty.")
        sys.exit(1)
    main()
