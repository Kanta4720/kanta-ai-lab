import json
from datetime import datetime, timezone, timedelta
import feedparser

JST = timezone(timedelta(hours=9))

FEEDS = [
    {"source": "Reuters", "category": "Business",
     "url": "https://feeds.reuters.com/reuters/businessNews"},
    {"source": "BBC Business", "category": "Business",
     "url": "http://feeds.bbci.co.uk/news/business/rss.xml"},
]

items = []

for feed in FEEDS:
    d = feedparser.parse(feed["url"])
    for e in d.entries[:5]:
        items.append({
            "source": feed["source"],
            "category": feed["category"],
            "title": e.title,
            "summary": getattr(e, "summary", "")[:200],
            "url": e.link
        })

now = datetime.now(JST).strftime("%Y-%m-%d %H:%M")

data = {
    "generated_at_jst": now,
    "items": items
}

with open("news.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
