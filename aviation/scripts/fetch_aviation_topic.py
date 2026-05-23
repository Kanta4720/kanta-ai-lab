#!/usr/bin/env python
# coding: utf-8

import os
import json
import feedparser
import trafilatura
from openai import OpenAI
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))

FEEDS = [
    {"source": "Simple Flying", "url": "https://simpleflying.com/feed/"},
    {"source": "AeroTime", "url": "https://aerotime.aero/feed"},
    {"source": "Airways Magazine", "url": "https://airwaysmag.com/feed/"},
    {"source": "Leeham News", "url": "https://leehamnews.com/feed/"},
    {"source": "Reuters", "url": "https://feeds.reuters.com/reuters/businessNews"},
    {"source": "CNBC", "url": "https://www.cnbc.com/id/10000664/device/rss/rss.html"},
    {"source": "APEX", "url": "https://apex.aero/feed/"},
]

OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")

client = OpenAI()

def fetch_headlines():
    headlines = []
    for feed in FEEDS:
        try:
            d = feedparser.parse(feed["url"])
            for entry in d.entries[:3]:
                headlines.append(f"[{feed['source']}] {entry.title}")
        except Exception as e:
            print(f"Could not parse feed {feed['url']}: {e}")
    return headlines

def load_todays_articles():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    news_path = os.path.join(os.path.dirname(script_dir), "news.json")
    try:
        with open(news_path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("todays_brief", [])
    except Exception as e:
        print(f"Could not load news.json: {e}")
        return []

def generate_world_topic(headlines, articles):
    articles_text = "\n".join([
        f"- {a['title']}: {a.get('summary_2lines', '')}"
        for a in articles
    ])

    headlines_text = "\n".join(headlines[:20])

    prompt = f"""本日の航空業界ニュースをもとに、航空機リース業界のプロフェッショナル向けに深掘り解説記事を1本生成してください。

本日の主要ニュース:
{articles_text}

RSSヘッドライン一覧:
{headlines_text}

以下のJSON形式で出力してください:
{{
  "topic": "深掘りするトピックのタイトル（日本語、30文字以内）",
  "news_connection": "本日のどのニュースと関連するか（例: 本日のFleet & Ordersニュースより）",
  "headline": "記事のキャッチーなサブタイトル（日本語）",
  "lead": "200字程度のリード文（日本語）",
  "sections": [
    {{
      "title": "セクション1のタイトル",
      "body": "セクション1の本文（300字程度）"
    }},
    {{
      "title": "セクション2のタイトル",
      "body": "セクション2の本文（300字程度）"
    }},
    {{
      "title": "セクション3のタイトル",
      "body": "セクション3の本文（300字程度）"
    }}
  ],
  "lease_insight": "航空機リース業界への具体的な示唆・インサイト（200字程度）",
  "key_takeaway": "読者への一言まとめ（100字程度）",
  "related_keywords": ["キーワード1", "キーワード2", "キーワード3", "キーワード4", "キーワード5"]
}}
"""

    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You are an expert aviation and aircraft leasing industry analyst and journalist. Write in Japanese."},
                {"role": "user", "content": prompt}
            ]
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"Error generating world topic: {e}")
        return None

def main():
    print("Fetching aviation headlines...")
    headlines = fetch_headlines()
    print(f"Fetched {len(headlines)} headlines")

    articles = load_todays_articles()
    print(f"Loaded {len(articles)} articles from news.json")

    print("Generating aviation world topic with AI...")
    topic_data = generate_world_topic(headlines, articles)

    if not topic_data:
        print("ERROR: Failed to generate world topic")
        return

    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    topic_data["generated_at_jst"] = now

    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(os.path.dirname(script_dir), "world_topic.json")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(topic_data, f, ensure_ascii=False, indent=2)

    print(f"Successfully generated world_topic.json at {output_path}")

if __name__ == "__main__":
    if "OPENAI_API_KEY" not in os.environ:
        print("Error: OPENAI_API_KEY environment variable not set.")
    else:
        main()
