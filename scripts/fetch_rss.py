#!/usr/bin/env python
# coding: utf-8

import os
import json
import feedparser
import trafilatura
from openai import OpenAI
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- 設定 --- #

# JSTタイムゾーン
JST = timezone(timedelta(hours=9))

# 取得するRSSフィード
# Financial Times, BloombergはRSSフィードが有料もしくは制限が強いため、代替ソースを含めています。
FEEDS = [
    {"source": "Reuters", "category": "Business", "url": "https://feeds.reuters.com/reuters/businessNews"},
    {"source": "BBC Business", "category": "Business", "url": "http://feeds.bbci.co.uk/news/business/rss.xml"},
    {"source": "CNBC", "category": "Business", "url": "https://www.cnbc.com/id/10000664/device/rss/rss.html"},
    {"source": "The Economist", "category": "Business", "url": "https://www.economist.com/business/rss.xml"},
    {"source": "Associated Press", "category": "Business", "url": "https://apnews.com/hub/business/rss.xml"},
]

# OpenAI APIクライアントの初期化
# APIキーは環境変数 `OPENAI_API_KEY` から自動的に読み込まれます。
client = OpenAI()

# --- 関数定義 --- #

def fetch_article_content(url):
    """記事URLから本文を抽出する"""
    downloaded = trafilatura.fetch_url(url)
    if downloaded:
        # `deduplicate=True` で重複するコンテンツの削除を試みる
        return trafilatura.extract(downloaded, include_comments=False, include_tables=False, deduplicate=True)
    return None

def analyze_article_with_ai(content, title):
    """AIを使って記事を分析・要約する"""
    if not content:
        return None

    prompt = f"""以下のニュース記事を分析し、指定されたJSON形式で出力してください。

記事タイトル: {title}
記事本文:
{content[:4000]} # トークン数削減のため本文を制限

出力形式:
{{
  "summary_2lines": "2行で理解できる簡潔な要約",
  "why_it_matters": "このニュースがなぜ重要なのか、背景や文脈を説明",
  "market_impact": "市場・企業・経済への具体的な影響を分析",
  "category": "[Tech, Markets, Geopolitics, Economy, Corporate] の中から最も適切なものを1つ選択"
}}
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You are a professional financial news analyst."},
                {"role": "user", "content": prompt}
            ]
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"Error analyzing article with AI for title '{title}': {e}")
        return None

def select_top5_articles(articles):
    """AIを使って重要記事TOP5を選定する"""
    if not articles:
        return []
        
    articles_for_ranking = []
    for i, article in enumerate(articles):
        articles_for_ranking.append(f"{i}: {article['title']} - {article['summary_2lines']}")

    prompt = f"""以下のニュースリストから、今日のビジネスパーソンにとって最も重要なニュースを5つ選び、そのインデックス番号をJSON配列で返してください。重要度の判断は、市場への影響、地政学的リスク、技術的なブレークスルーなどを考慮してください。

ニュースリスト:
{json.dumps(articles_for_ranking, indent=2)}

出力形式:
{{
  "top5_indices": [番号1, 番号2, 番号3, 番号4, 番号5]
}}
"""
    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You are an expert editor for a business news brief."},
                {"role": "user", "content": prompt}
            ]
        )
        result = json.loads(response.choices[0].message.content)
        top5_indices = result.get("top5_indices", [])
        # インデックスの範囲チェックを追加
        return [articles[i] for i in top5_indices if i < len(articles)]
    except Exception as e:
        print(f"Error selecting top 5 articles: {e}")
        return articles[:5] # エラー時は先頭5件を返す

def process_entry(entry, feed_source):
    """単一のRSSエントリーを処理する"""
    print(f"Processing: {entry.title}")
    try:
        content = fetch_article_content(entry.link)
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
            "market_impact": ai_analysis.get("market_impact", ""),
            "category": ai_analysis.get("category", feed_source["category"]),
            "source": feed_source["source"],
            "url": entry.link
        }
    except Exception as e:
        print(f"Error processing entry '{entry.title}': {e}")
        return None

# --- メイン処理 --- #

def main():
    all_articles = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_entry = {}
        for feed in FEEDS:
            try:
                d = feedparser.parse(feed["url"])
                # 各ソースから5件ずつ取得
                for entry in d.entries[:5]:
                    future = executor.submit(process_entry, entry, feed)
                    future_to_entry[future] = entry.title
            except Exception as e:
                print(f"Could not parse RSS feed {feed['url']}: {e}")

        for future in as_completed(future_to_entry):
            try:
                result = future.result()
                if result:
                    all_articles.append(result)
            except Exception as e:
                title = future_to_entry[future]
                print(f"Future for '{title}' generated an exception: {e}")

    # カテゴリ別に記事を整理
    categories = {cat: [] for cat in ["Tech", "Markets", "Geopolitics", "Economy", "Corporate"]}
    for article in all_articles:
        if article["category"] in categories:
            categories[article["category"]].append(article)

    # 重要ニュースTOP5を選定
    todays_brief = select_top5_articles(all_articles)

    # JSONファイルに出力
    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    output_data = {
        "generated_at_jst": now,
        "todays_brief": todays_brief,
        "categories": categories
    }

    # プロジェクトルートに news.json を出力
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    output_path = os.path.join(project_root, "news.json")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print(f"Successfully generated news.json at {output_path}")

if __name__ == "__main__":
    # GitHub Actionsで実行されることを想定し、APIキーの存在チェック
    if "OPENAI_API_KEY" not in os.environ:
        print("Error: OPENAI_API_KEY environment variable not set.")
    else:
        main()
