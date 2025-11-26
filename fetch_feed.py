import os
import yaml
import feedparser
import pandas as pd
from datetime import datetime, timezone

CONFIG_FEEDS = "config/feeds.yaml"
DATA_DIR = "data/raw"


def load_feeds():
    with open(CONFIG_FEEDS, "r") as f:
        cfg = yaml.safe_load(f)
    return cfg["feeds"]


def fetch_feed(feed):
    url = feed["url"]
    parsed = feedparser.parse(url)
    rows = []
    for e in parsed.entries:
        rows.append({
            "feed_id": feed["id"],
            "feed_name": feed["name"],
            "tags": ",".join(feed.get("tags", [])),
            "title": getattr(e, "title", ""),
            "link": getattr(e, "link", ""),
            "summary": getattr(e, "summary", ""),
            "published": getattr(e, "published", ""),
            "fetched_at": datetime.now(timezone.utc).isoformat()
        })
    return rows


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    feeds = load_feeds()
    all_rows = []

    for feed in feeds:
        try:
            rows = fetch_feed(feed)
            all_rows.extend(rows)
            print(f"Fetched {len(rows)} items from {feed['name']}")
        except Exception as e:
            print(f"Error fetching {feed['name']}: {e}")

    if not all_rows:
        print("No data fetched.")
        return

    df = pd.DataFrame(all_rows)
    today = datetime.now().strftime("%Y-%m-%d")
    out_path = os.path.join(DATA_DIR, f"news_{today}.csv")
    df.to_csv(out_path, index=False)
    print(f"Saved {len(df)} rows to {out_path}")


if __name__ == "__main__":
    main()
