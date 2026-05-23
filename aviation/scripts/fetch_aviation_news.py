#!/usr/bin/env python
# coding: utf-8

import os
import sys
import json
import re
import difflib
import feedparser
import trafilatura
from openai import OpenAI
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- 設定 --- #

JST = timezone(timedelta(hours=9))

FEEDS = [
    {"source": "Simple Flying", "category": "Fleet & Orders", "url": "https://simpleflying.com/feed/"},
    {"source": "AeroTime", "category": "Airline Finance", "url": "https://aerotime.aero/feed"},
    {"source": "Airways Magazine", "category": "Sustainability", "url": "https://airwaysmag.com/feed/"},
    {"source": "Leeham News", "category": "Fleet & Orders", "url": "https://leehamnews.com/feed/"},
    {"source": "Reuters", "category": "Airline Finance", "url": "https://feeds.reuters.com/reuters/businessNews"},
    {"source": "CNBC", "category": "Airline Finance", "url": "https://www.cnbc.com/id/10000664/device/rss/rss.html"},
    {"source": "APEX", "category": "Sustainability", "url": "https://apex.aero/feed/"},
]

CATEGORIES = ["Lease Market", "Fleet & Orders", "Airline Finance", "Regulations", "Geopolitics", "Sustainability"]

ARTICLES_PER_FEED = 3

OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")

client = OpenAI()

DEDUP_THRESHOLD = 0.65

# --- 関数定義 --- #

def normalize_title(title):
    return re.sub(r'[^\w\s]', '', title.lower())

def deduplicate_entries(entries):
    seen_urls = set()
    seen_titles = []
    unique = []

    for entry, feed_source in entries:
        if entry.link in seen_urls:
            print(f"[DEDUP] URL重複をスキップ: {entry.title}")
            continue
        seen_urls.add(entry.link)

        norm = normalize_title(entry.title)
        is_dup = any(
            difflib.SequenceMatcher(None, norm, t).ratio() >= DEDUP_THRESHOLD
            for t in seen_titles
        )
        if is_dup:
            print(f"[DEDUP] タイトル類似重複をスキップ: {entry.title}")
            continue

        seen_titles.append(norm)
        unique.append((entry, feed_source))

    print(f"[DEDUP] {len(entries)}件 → {len(unique)}件（{len(entries) - len(unique)}件除去）")
    return unique

def fetch_article_content(url):
    downloaded = trafilatura.fetch_url(url)
    if downloaded:
        text = trafilatura.extract(downloaded, include_comments=False, include_tables=False, deduplicate=True)
        if text:
            return text
    return None

def analyze_article_with_ai(content, title):
    if not content:
        return None

    prompt = f"""以下の航空業界ニュース記事を分析し、指定されたJSON形式で出力してください。

記事タイトル: {title}
記事本文:
{content[:4000]}

出力形式:
{{
  "summary_2lines": "2行で理解できる簡潔な要約（日本語）",
  "why_it_matters": "このニュースが航空・リース業界にとってなぜ重要なのか、背景や文脈を説明（日本語）",
  "lease_impact": "航空機リース市場・リース会社への具体的な影響を分析（日本語）",
  "category": "以下の基準で最適なカテゴリを1つ選択: Lease Market（リース契約・市場動向・SLB・レート）/ Fleet & Orders（機材発注・納入・新型機）/ Airline Finance（航空会社財務・決算・破綻・再建）/ Regulations（規制・耐空性・安全・環境規制）/ Geopolitics（国際関係・貿易摩擦・地政学リスク・制裁）/ Sustainability（SAF・脱炭素・ESG・サステナビリティ）"
}}
"""

    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You are an expert aviation and aircraft leasing industry analyst. Respond in Japanese."},
                {"role": "user", "content": prompt}
            ]
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"Error analyzing article with AI for title '{title}': {e}")
        return None

def select_top5_articles(articles):
    if not articles:
        return []

    articles_for_ranking = []
    for i, article in enumerate(articles):
        articles_for_ranking.append(f"{i}: {article['title']} - {article['summary_2lines']}")

    prompt = f"""以下の航空業界ニュースリストから、航空機リース業界のプロフェッショナルにとって最も重要なニュースを5つ選び、そのインデックス番号をJSON配列で返してください。
重要度の判断は、リース市場への影響、航空会社の財務健全性、規制・地政学リスク、機材トレンドなどを考慮してください。

ニュースリスト:
{json.dumps(articles_for_ranking, ensure_ascii=False, indent=2)}

出力形式:
{{
  "top5_indices": [番号1, 番号2, 番号3, 番号4, 番号5]
}}
"""
    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You are an expert editor for an aviation leasing industry news brief."},
                {"role": "user", "content": prompt}
            ]
        )
        result = json.loads(response.choices[0].message.content)
        top5_indices = result.get("top5_indices", [])
        return [articles[i] for i in top5_indices if i < len(articles)]
    except Exception as e:
        print(f"Error selecting top 5 articles: {e}")
        return articles[:5]

def process_entry(entry, feed_source):
    print(f"Processing: {entry.title}")
    try:
        content = fetch_article_content(entry.link)
        if not content:
            content = getattr(entry, 'summary', None) or getattr(entry, 'description', None)
        if not content:
            print(f"Could not fetch content for: {entry.title}")
            return None

        ai_analysis = analyze_article_with_ai(content, entry.title)
        if not ai_analysis:
            return None

        return {
            "title": entry.title,
            "summary_2lines": ai_analysis.get("summary_2lines", ""),
            "why_it_matters": ai_analysis.get("why_it_matters", ""),
            "lease_impact": ai_analysis.get("lease_impact", ""),
            "category": ai_analysis.get("category", feed_source["category"]),
            "source": feed_source["source"],
            "url": entry.link
        }
    except Exception as e:
        print(f"Error processing entry '{entry.title}': {e}")
        return None

# --- メイン処理 --- #

def main():
    all_entries = []
    for feed in FEEDS:
        try:
            d = feedparser.parse(feed["url"])
            for entry in d.entries[:ARTICLES_PER_FEED]:
                all_entries.append((entry, feed))
        except Exception as e:
            print(f"Could not parse RSS feed {feed['url']}: {e}")

    unique_entries = deduplicate_entries(all_entries)

    all_articles = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_entry = {}
        for entry, feed in unique_entries:
            future = executor.submit(process_entry, entry, feed)
            future_to_entry[future] = entry.title

        for future in as_completed(future_to_entry):
            try:
                result = future.result()
                if result:
                    all_articles.append(result)
            except Exception as e:
                title = future_to_entry[future]
                print(f"Future for '{title}' generated an exception: {e}")

    categories = {cat: [] for cat in CATEGORIES}
    for article in all_articles:
        if article["category"] in categories:
            categories[article["category"]].append(article)

    if not all_articles:
        print("ERROR: 記事を1件も取得できませんでした。ワークフローを失敗させます。")
        sys.exit(1)

    print(f"[INFO] 合計 {len(all_articles)} 件の記事を取得しました。")

    todays_brief = select_top5_articles(all_articles)

    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    output_data = {
        "generated_at_jst": now,
        "todays_brief": todays_brief,
        "categories": categories
    }

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    output_path = os.path.join(project_root, "news.json")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print(f"Successfully generated news.json at {output_path}")

if __name__ == "__main__":
    if "OPENAI_API_KEY" not in os.environ:
        print("Error: OPENAI_API_KEY environment variable not set.")
    else:
        main()
