#!/usr/bin/env python3
"""Build a deduplicated client-side search index from archived aviation news."""

import json
import os
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


ARCHIVE_FILE_RE = re.compile(r"^news_(\d{4}-\d{2}-\d{2})\.json$")
TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "ref"}


def canonical_url(url):
    """Remove harmless URL differences so repeated archive entries collapse."""
    parts = urlsplit(url.strip())
    query = [(key, value) for key, value in parse_qsl(parts.query) if key.lower() not in TRACKING_PARAMS]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), ""))


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    aviation_dir = os.path.dirname(script_dir)
    archive_dir = os.path.join(aviation_dir, "archive")
    articles_by_url = {}
    latest_generated_at = ""

    filenames = sorted(os.listdir(archive_dir), reverse=True)
    for filename in filenames:
        match = ARCHIVE_FILE_RE.match(filename)
        if not match:
            continue
        date = match.group(1)
        with open(os.path.join(archive_dir, filename), encoding="utf-8") as handle:
            data = json.load(handle)
        if not latest_generated_at:
            latest_generated_at = data.get("generated_at_jst", "")

        for category_articles in data.get("categories", {}).values():
            for article in category_articles:
                url = article.get("url", "").strip()
                if not url:
                    continue
                key = canonical_url(url)
                if key not in articles_by_url:
                    record = dict(article)
                    record["url"] = url
                    record["dates"] = []
                    articles_by_url[key] = record
                record = articles_by_url[key]
                if date not in record["dates"]:
                    record["dates"].append(date)

    articles = list(articles_by_url.values())
    articles.sort(key=lambda article: (article["dates"][0], article.get("published_at", "")), reverse=True)
    output = {
        "generated_at_jst": latest_generated_at,
        "article_count": len(articles),
        "articles": articles,
    }
    output_path = os.path.join(aviation_dir, "search-index.json")
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(output, handle, ensure_ascii=False, indent=2)
    print(f"Search index built: {len(articles)} unique articles")


if __name__ == "__main__":
    main()
