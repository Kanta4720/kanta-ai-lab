#!/usr/bin/env python
# coding: utf-8

import os
import json
import requests
import trafilatura
from openai import OpenAI
from datetime import datetime, timezone, timedelta

JST          = timezone(timedelta(hours=9))
NEWS_API_KEY = os.environ.get("NEWS_API_KEY")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")

client = OpenAI()

# 深掘り・特集系の記事を探すクエリ（直近3日間）
FEATURE_QUERIES = [
    "aviation industry analysis future",
    "aircraft technology innovation explainer",
    "airline strategy business model",
    "airport infrastructure development",
    "aviation history record milestone",
    "pilot shortage crew training aviation",
    "space aviation supersonic electric aircraft",
]

CATEGORIES = [
    "Industry Analysis", "Future of Aviation", "Airline Strategy",
    "Aircraft Technology", "Airport & Infrastructure", "People & Culture"
]


def fetch_candidates():
    """NewsAPI から特集候補記事を収集する（直近3日間）"""
    if not NEWS_API_KEY:
        print("[NewsAPI] NEWS_API_KEY が未設定。スキップ。")
        return []

    from_date = (datetime.now(timezone.utc) - timedelta(days=3)).strftime('%Y-%m-%dT%H:%M:%SZ')
    candidates = []

    for q in FEATURE_QUERIES:
        try:
            resp = requests.get(
                "https://newsapi.org/v2/everything",
                params={
                    "q":        q,
                    "language": "en",
                    "sortBy":   "relevancy",
                    "from":     from_date,
                    "pageSize": 5,
                    "apiKey":   NEWS_API_KEY,
                },
                timeout=15,
            )
            data = resp.json()
            if data.get("status") != "ok":
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

                candidates.append({
                    "title":       title,
                    "url":         url,
                    "source":      art.get("source", {}).get("name", ""),
                    "content":     combined,
                    "published_at": pub_date,
                })
        except Exception as e:
            print(f"[NewsAPI] クエリ失敗 '{q}': {e}")

    print(f"[候補] {len(candidates)} 件収集")
    return candidates


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


def select_and_summarize(candidates):
    """AI で面白い記事を3〜5本選び、日本語要約を生成する"""
    if not candidates:
        return []

    # 候補リストを AI に渡して選定
    listing = [f"{i}: [{c['source']}] {c['title']}" for i, c in enumerate(candidates)]
    select_prompt = f"""以下の航空業界ニュース候補から、航空業界に興味を持つ読者にとって「面白い・知識が深まる・驚きがある」記事を最大5本選んでください。
単純な速報ニュースより、背景解説・特集・技術・人間ドラマ系の記事を優先してください。

候補リスト:
{json.dumps(listing, ensure_ascii=False, indent=2)}

出力形式: {{"selected_indices": [番号1, 番号2, ...]}}
"""
    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You are a curator for an aviation industry magazine."},
                {"role": "user",   "content": select_prompt},
            ],
        )
        result  = json.loads(resp.choices[0].message.content)
        indices = result.get("selected_indices", [])[:5]
        selected = [candidates[i] for i in indices if i < len(candidates)]
    except Exception as e:
        print(f"[選定エラー] {e}")
        selected = candidates[:5]

    print(f"[選定] {len(selected)} 本を選択")

    # 各記事を要約
    features = []
    for art in selected:
        content = art["content"]
        if len(content) < 200:
            full = fetch_full_content(art["url"])
            if full:
                content = full

        if not content:
            continue

        summary_prompt = f"""以下の航空業界記事を日本語で要約してください。

記事タイトル: {art['title']}
記事内容:
{content[:4000]}

出力形式:
{{
  "title_ja": "日本語の見出し（読者が思わず読みたくなるような魅力的なタイトル、30文字以内）",
  "summary": "記事の内容を5〜7文で詳しく要約（日本語）。背景・経緯・なぜ重要か・今後の展望まで含めて書く。読者が原文を読まなくても十分理解できるレベルで",
  "key_points": ["要点1（日本語）", "要点2（日本語）", "要点3（日本語）"],
  "category": "Industry Analysis / Future of Aviation / Airline Strategy / Aircraft Technology / Airport & Infrastructure / People & Culture のいずれか1つ",
  "reading_minutes": 記事を読むのにかかる推定分数（整数）
}}
"""
        try:
            resp = client.chat.completions.create(
                model=OPENAI_MODEL,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": "You are an aviation journalist who writes for a Japanese audience. Always respond in Japanese."},
                    {"role": "user",   "content": summary_prompt},
                ],
            )
            result = json.loads(resp.choices[0].message.content)
            features.append({
                "title":          result.get("title_ja", art["title"]),
                "original_title": art["title"],
                "source":         art["source"],
                "url":            art["url"],
                "published_at":   art["published_at"],
                "category":       result.get("category", "Industry Analysis"),
                "reading_minutes": result.get("reading_minutes", 3),
                "summary":        result.get("summary", ""),
                "key_points":     result.get("key_points", []),
            })
            print(f"  ✓ 要約完了: {result.get('title_ja', '')[:40]}")
        except Exception as e:
            print(f"  ✗ 要約失敗 '{art['title'][:50]}': {e}")

    return features


def main():
    print("航空特集記事を収集・要約中...")

    candidates = fetch_candidates()
    if not candidates:
        print("ERROR: 候補記事を取得できませんでした。")
        return

    features = select_and_summarize(candidates)
    if not features:
        print("ERROR: 特集記事の生成に失敗しました。")
        return

    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    output = {
        "generated_at_jst": now,
        "features": features,
    }

    script_dir  = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(os.path.dirname(script_dir), "features.json")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Successfully generated features.json ({len(features)} 本) at {output_path}")


if __name__ == "__main__":
    if "OPENAI_API_KEY" not in os.environ:
        print("Error: OPENAI_API_KEY environment variable not set.")
    else:
        main()
