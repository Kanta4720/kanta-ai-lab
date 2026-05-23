#!/usr/bin/env python3
import os
import json
import re

def main():
    script_dir   = os.path.dirname(os.path.abspath(__file__))
    aviation_dir = os.path.dirname(script_dir)
    archive_dir  = os.path.join(aviation_dir, "archive")
    os.makedirs(archive_dir, exist_ok=True)

    pattern = re.compile(r'^news_(\d{4}-\d{2}-\d{2})\.json$')
    dates = set()
    for fname in os.listdir(archive_dir):
        m = pattern.match(fname)
        if m:
            dates.add(m.group(1))

    sorted_dates = sorted(dates, reverse=True)

    index_path = os.path.join(archive_dir, "index.json")
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump({"dates": sorted_dates}, f, ensure_ascii=False, indent=2)

    print(f"Archive index updated: {len(sorted_dates)} dates available")

if __name__ == "__main__":
    main()
