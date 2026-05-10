#!/usr/bin/env python
# coding: utf-8

import os
import sys
import json
import random
from openai import OpenAI
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")
client = OpenAI()

TOPICS = [
    # アフリカ
    "ナイジェリア・ラゴスの屋台文化とストリートフード",
    "エチオピアの急成長するスタートアップ生態系",
    "ケニアのMペサが変えたデジタル決済革命",
    "ガーナの若者が作るアフリカンファッション",
    # 北欧・欧州
    "フィンランドの高校教育と「学習の喜び」哲学",
    "ノルウェーの政府系ファンドが世界最大になった理由",
    "スウェーデンの「ラゴム」文化と独特の仕事観",
    "北欧の恋愛文化と男女平等の実態",
    "ドイツの職人制度「マイスター」が今も生きる理由",
    "スイスの時計産業と精密さへの執着",
    "ポーランドのゲーム産業が世界を席巻している理由",
    # 中東
    "ドバイ富豪の1日とその裏側",
    "サウジアラビアのビジョン2030が変える若者の生活",
    "イスラエルのスタートアップ国家としての強さの秘密",
    "カタールがW杯を機に変えたもの",
    # アジア
    "中国・深センの製造業とイノベーションの最前線",
    "シンガポールの教育システムと超競争社会の光と影",
    "インド・バンガロールのITエンジニアの日常",
    "韓国の「빨리빨리（パリパリ）」文化とその功罪",
    "台湾の半導体産業と普通の人々の暮らし",
    "タイのデジタルノマドが集まる理由",
    "ベトナムの若い製造業大国への転換",
    # 南米
    "ブラジル・ファベーラに生きる起業家精神",
    "コロンビアの驚くべき変貌と観光大国への挑戦",
    "アルゼンチンのインフレ経済の中で生きる人々",
    # 北米
    "シリコンバレーの「失敗を称える」カルチャー",
    "メキシコシティの巨大都市で生きる若者たち",
    "カナダの多文化主義が作る独特のアイデンティティ",
    # その他
    "ニュージーランドの先住民マオリ文化と現代社会",
    "アイスランドの人口33万人の超小国が世界で存在感を示す理由",
]


def generate_topic_article(topic: str) -> dict:
    prompt = f"""今日の世界特集テーマ：「{topic}」

このテーマについて、好奇心旺盛な日本の20〜40代向けに、面白くてためになる記事を作成してください。
単なる説明でなく、「へぇ！」と驚く視点や、日本との比較を入れてください。

出力形式（JSON）:
{{
  "topic": "{topic}",
  "headline": "読者が思わずクリックしたくなるキャッチーな見出し（20文字前後）",
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
            {"role": "system", "content": "あなたは世界各地の文化・社会・経済を面白く紹介するジャーナリストです。読者の知的好奇心を刺激し、世界が広がる体験を届けてください。"},
            {"role": "user", "content": prompt}
        ]
    )
    return json.loads(response.choices[0].message.content)


def main():
    today = datetime.now(JST).strftime("%Y-%m-%d")
    random.seed(today + "_world")
    topic = random.choice(TOPICS)
    print(f"今日のトピック: {topic}")

    data = generate_topic_article(topic)
    data["generated_at_jst"] = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    data["date"] = today

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    output_path = os.path.join(project_root, "world_topic.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"world_topic.json を生成しました: {output_path}")


if __name__ == "__main__":
    if "OPENAI_API_KEY" not in os.environ:
        print("Error: OPENAI_API_KEY が設定されていません。")
        sys.exit(1)
    main()
