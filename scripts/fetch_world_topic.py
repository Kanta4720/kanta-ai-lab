#!/usr/bin/env python
# coding: utf-8

import os
import sys
import json
from openai import OpenAI
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")
client = OpenAI()


def load_todays_news(project_root: str) -> list[dict]:
    """fetch_rss.py が生成した news.json からヘッドラインを取得する"""
    news_path = os.path.join(project_root, "news.json")
    try:
        with open(news_path, encoding="utf-8") as f:
            data = json.load(f)
        articles = data.get("todays_brief", [])
        # カテゴリ別の記事も含めて最大20件収集
        for cat_articles in data.get("categories", {}).values():
            for a in cat_articles:
                if a not in articles:
                    articles.append(a)
        return articles[:20]
    except Exception as e:
        print(f"[WARN] news.json の読み込みに失敗しました: {e}")
        return []


def generate_topic_article(news_headlines: list[dict]) -> dict:
    # ニュース一覧をテキスト化してプロンプトに埋め込む
    news_text = "\n".join(
        f"- [{a.get('category', '')}] {a.get('title', '')}（{a.get('source', '')}）"
        for a in news_headlines
    ) if news_headlines else "（本日のニュースデータなし）"

    prompt = f"""今日の世界のビジネスニュース一覧:
{news_text}

【タスク】
上記のニュースを踏まえ、今日の世界で注目すべき「文化・社会・ライフスタイル」のトピックを1つ選び、深掘り特集記事を作成してください。

選び方のポイント:
- ニュースと直接つながる国・地域・社会現象を選ぶ（例: 貿易摩擦のニュースがあれば「中国の深セン工場の実態」、AIニュースがあれば「シリコンバレーの働き方」など）
- ビジネスニュースそのものではなく、その背景にある「人・文化・社会」にフォーカスする
- 日本の読者が「へぇ！」と驚く視点を必ず入れる

出力形式（JSON）:
{{
  "topic": "選んだトピック（20文字前後）",
  "news_connection": "今日のどのニュースと関連して選んだか（1文）",
  "headline": "読者が思わずクリックしたくなる見出し（25文字前後）",
  "lead": "記事のつかみとなるリード文。最初の1文で引き込む（3文程度）",
  "sections": [
    {{"subtitle": "小見出し（10文字前後）", "content": "本文（4〜5文。具体的なエピソードや数字を入れる）"}},
    {{"subtitle": "小見出し（10文字前後）", "content": "本文（4〜5文。日本との違いや共通点を入れる）"}},
    {{"subtitle": "小見出し（10文字前後）", "content": "本文（4〜5文。ビジネスや未来への示唆）"}}
  ],
  "key_insight": "このテーマからビジネスパーソンが得られる最大の示唆（2〜3文）",
  "fun_fact": "「知らなかった！」と思う豆知識（1〜2文）",
  "related_keywords": ["関連キーワード1", "関連キーワード2", "関連キーワード3"]
}}"""

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": "あなたは世界各地の文化・社会・経済を面白く紹介するジャーナリストです。今日のホットなニュースと連動しながら、読者の知的好奇心を刺激する特集記事を届けてください。"},
            {"role": "user", "content": prompt}
        ]
    )
    return json.loads(response.choices[0].message.content)


def main():
    today = datetime.now(JST).strftime("%Y-%m-%d")
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    news = load_todays_news(project_root)
    print(f"[INFO] 今日のニュース {len(news)} 件を参照してトピックを生成します")

    data = generate_topic_article(news)
    data["generated_at_jst"] = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    data["date"] = today

    print(f"[INFO] 今日のトピック: {data.get('topic', '?')}")
    print(f"[INFO] 選定理由: {data.get('news_connection', '?')}")

    output_path = os.path.join(project_root, "world_topic.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"[INFO] world_topic.json を生成しました")


if __name__ == "__main__":
    if "OPENAI_API_KEY" not in os.environ:
        print("Error: OPENAI_API_KEY が設定されていません。")
        sys.exit(1)
    main()
