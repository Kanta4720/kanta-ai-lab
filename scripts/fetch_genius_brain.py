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

GENIUSES = [
    {
        "name": "イーロン・マスク",
        "en_name": "Elon Musk",
        "role": "Tesla / SpaceX / X オーナー",
        "persona": "火星移住・電気自動車・AIの未来を本気で信じる破壊的イノベーター。政治にも積極介入し、常に常識の外側を走る。",
        "emoji": "🚀"
    },
    {
        "name": "サム・アルトマン",
        "en_name": "Sam Altman",
        "role": "OpenAI CEO",
        "persona": "AGIが人類の未来を変えると確信するビジョナリー。政府・投資家・研究者との外交を同時にこなす。リスクを語りながらも全速前進。",
        "emoji": "🤖"
    },
    {
        "name": "孫正義",
        "en_name": "Masayoshi Son",
        "role": "SoftBank Group 会長兼社長",
        "persona": "300年先のビジョンを語る投資家。AIと半導体に全てを賭け、失敗を恐れず超大型ベットを繰り返す日本最大の夢想家。",
        "emoji": "💰"
    },
    {
        "name": "ジェンスン・ファン",
        "en_name": "Jensen Huang",
        "role": "NVIDIA CEO",
        "persona": "GPUで世界のAIインフラを握った半導体の帝王。技術の細部まで語れる職人気質と、業界全体を動かす政治力を併せ持つ。",
        "emoji": "⚡"
    },
    {
        "name": "ドナルド・トランプ",
        "en_name": "Donald Trump",
        "role": "米国第47代大統領",
        "persona": "「アメリカ・ファースト」を体現する交渉人。メディアの空気を読んで支持者を鼓舞し、経済・外交・国内政治を同時に動かす。",
        "emoji": "🇺🇸"
    },
]


def generate_genius_brain(genius: dict) -> dict:
    prompt = f"""今日は{genius['name']}（{genius['role']}）の脳内を推測します。

人物像: {genius['persona']}

現在の世界情勢と最新のビジネス・政治ニュースを踏まえ、今日の{genius['name']}が考えていそうなことを
「今日の戦略メモ」としてAIが推測・創作してください。
あくまでエンターテインメントとして、その人物らしいロジックと口調で書いてください。

出力形式（JSON）:
{{
  "person": "{genius['name']}",
  "en_name": "{genius['en_name']}",
  "role": "{genius['role']}",
  "emoji": "{genius['emoji']}",
  "mood_today": "今日の気分・テンション（例：「強気」「焦り気味」「静かな自信」）",
  "top_of_mind": "今この瞬間、頭の中で最大のスペースを占めていること（1〜2文）",
  "strategy_memos": [
    {{"theme": "テーマ名（5〜10文字）", "thought": "その人物らしい考え方・分析（3〜4文。一人称・その人の口調で）"}},
    {{"theme": "テーマ名（5〜10文字）", "thought": "その人物らしい考え方・分析（3〜4文）"}},
    {{"theme": "テーマ名（5〜10文字）", "thought": "その人物らしい考え方・分析（3〜4文）"}}
  ],
  "todays_quote": "今日の彼が言いそうな名言・一言（その人物の口調で。20〜40文字）",
  "biggest_risk": "今最も警戒しているリスク（2〜3文）",
  "biggest_opportunity": "今最も興奮しているチャンス（2〜3文）",
  "what_competitors_dont_know": "競合・周囲がまだ気づいていない、彼だけが見えているもの（2〜3文）"
}}"""

    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": "あなたは世界のビジネスリーダーの思考パターンを深く研究している専門家です。エンターテインメントとして楽しめるよう、その人物らしいロジックと語り口で推測・創作してください。これはフィクションです。"},
            {"role": "user", "content": prompt}
        ]
    )
    return json.loads(response.choices[0].message.content)


def main():
    today = datetime.now(JST).strftime("%Y-%m-%d")
    random.seed(today + "_genius")
    genius = random.choice(GENIUSES)
    print(f"今日の天才: {genius['name']}")

    data = generate_genius_brain(genius)
    data["generated_at_jst"] = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
    data["date"] = today

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    output_path = os.path.join(project_root, "genius.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"genius.json を生成しました: {output_path}")


if __name__ == "__main__":
    if "OPENAI_API_KEY" not in os.environ:
        print("Error: OPENAI_API_KEY が設定されていません。")
        sys.exit(1)
    main()
