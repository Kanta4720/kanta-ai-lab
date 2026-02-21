# `fetch_rss.py` 改善案

現在の `fetch_rss.py` を、AIによる要約と分析、複数ソース対応、重要ニュースの自動抽出機能を持つように改善します。

## 改善のポイント

1.  **データソースの拡充**: 信頼性の高い海外ニュースソースのRSSフィードを追加します。
2.  **記事本文の抽出**: RSSフィードには通常、記事の全文は含まれていません。そのため、各記事のURLにアクセスし、本文を抽出する処理を追加します。`trafilatura`ライブラリを利用して、広告やメニューなどを除いた本文のみを効率的に抽出します。
3.  **AIによる分析と要約**: 抽出した本文をOpenAIのGPTモデルに渡し、以下の項目を生成します。
    *   `summary_2lines`: 2行での要約
    *   `why_it_matters`: ニュースの重要性（背景）
    *   `market_impact`: 市場や経済への影響
    *   `category`: 最適なカテゴリ
4.  **重要ニュースの選定**: 全ての記事をAIで分析した後、その日の最も重要なニュースTOP5 (`todays_brief`) を選定する処理を追加します。
5.  **並列処理による高速化**: 複数の記事を処理するには時間がかかります。`concurrent.futures`を使い、記事の取得とAIによる分析を並列で実行し、処理時間を大幅に短縮します。
6.  **APIキーの安全な管理**: OpenAIのAPIキーは、GitHub ActionsのSecrets機能を使って安全に管理します。スクリプトは環境変数 `OPENAI_API_KEY` からキーを読み込むように設計します。

## 新しい `fetch_rss.py` のコード

```python
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
        return trafilatura.extract(downloaded, include_comments=False, include_tables=False)
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
        print(f"Error analyzing article with AI: {e}")
        return None

def select_top5_articles(articles):
    """AIを使って重要記事TOP5を選定する"""
    articles_for_ranking = []
    for i, article in enumerate(articles):
        articles_for_ranking.append(f"{i}: {article['title']} - {article['summary_2lines']}")

    prompt = f"""以下のニュースリストから、今日のビジネスパーソンにとって最も重要なニュースを5つ選び、そのインデックス番号をJSON配列で返してください。

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
        return [articles[i] for i in top5_indices if i < len(articles)]
    except Exception as e:
        print(f"Error selecting top 5 articles: {e}")
        return articles[:5] # エラー時は先頭5件を返す

def process_entry(entry, feed_source):
    """単一のRSSエントリーを処理する"""
    print(f"Processing: {entry.title}")
    content = fetch_article_content(entry.link)
    if not content:
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

# --- メイン処理 --- #

def main():
    all_articles = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_entry = {}
        for feed in FEEDS:
            d = feedparser.parse(feed["url"])
            # 各ソースから5件ずつ取得
            for entry in d.entries[:5]:
                future = executor.submit(process_entry, entry, feed)
                future_to_entry[future] = entry.title

        for future in as_completed(future_to_entry):
            result = future.result()
            if result:
                all_articles.append(result)

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

    with open("news.json", "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print("Successfully generated news.json")

if __name__ == "__main__":
    main()

```

## GitHub Actionsの更新

`daily.yml`を更新して、新しいライブラリのインストールとAPIキーの設定を追加する必要があります。

```yaml
name: Daily News Update
on:
  schedule:
    - cron: "0 22 * * *"   # JST 07:00
  workflow_dispatch:
permissions:
  contents: write
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install dependencies
        run: |
          pip install feedparser trafilatura openai
      - name: Fetch and Analyze News
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: python scripts/fetch_rss.py
      - name: Commit changes
        run: |
          git config user.name "kanta-news-bot"
          git config user.email "actions@users.noreply.github.com"
          git add news.json
          git diff --cached --quiet || (git commit -m "Update AI news brief" && git push)
```

**【重要】**
このワークフローを動作させるには、GitHubリポジトリの `Settings > Secrets and variables > Actions` で、`OPENAI_API_KEY` という名前の新しいSecretを作成し、ご自身のOpenAI APIキーを設定していただく必要があります。

## 設計の意図

*   **品質と信頼性**: 複数の信頼できるニュースソースを統合することで、情報の網羅性と客観性を高めました。AIによる分析は、単なる要約に留まらず、「なぜ重要か」「市場への影響は何か」という付加価値を提供し、ユーザーが短時間で深い洞察を得られるように設計されています。
*   **パフォーマンス**: ニュース記事の取得とAI分析は時間がかかる処理ですが、並列処理を導入することで、GitHub Actionsの実行時間制限内に処理が完了するように最適化しています。
*   **保守性と拡張性**: `FEEDS`リストを編集するだけで、ニュースソースを簡単に追加・変更できます。AIのプロンプトを調整することで、出力の質を継続的に改善することも可能です。
*   **セキュリティ**: APIキーをコードに直接書き込まず、GitHubのSecrets機能を利用することで、キーが外部に漏洩するリスクを防ぎます。これはプロダクトレベルのアプリケーションにおける基本的なセキュリティ対策です。
