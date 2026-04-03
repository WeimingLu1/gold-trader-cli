"""Historical news headlines via NewsAPI.org for backtesting."""
from datetime import date, timedelta
import httpx

from app.config import get_settings
from app.history import cache


class NewsHistoryStore:
    """
    Fetches and caches gold/macro-relevant news headlines via NewsAPI.org.

    NewsAPI free tier allows fetching articles up to 1 month old.
    Caches results in SQLite to avoid repeated API calls.

    Usage:
        store = NewsHistoryStore()
        store.warm_cache(start_date, end_date)  # prefetch
        headlines = store.get_headlines(some_date)
    """

    QUERY = "gold OR XAUUSD OR Fed OR inflation OR dollar OR treasury OR safe haven"

    def warm_cache(self, start_date: date, end_date: date) -> int:
        """
        Pre-fetch news headlines for the entire date range via NewsAPI.

        Returns number of unique dates with headlines cached.
        Note: NewsAPI free tier only provides ~1 month of history.
        """
        settings = get_settings()
        api_key = settings.news_api_key

        if not api_key or api_key in ("", "your_news_api_key_here"):
            print("[NewsHistory] No NewsAPI key configured.")
            return 0

        # NewsAPI paginates — fetch up to 100 articles per page
        fetched_dates: set[date] = set()
        page = 1
        seen_urls: set[str] = set()

        while True:
            url = "https://newsapi.org/v2/everything"
            params = {
                "q": self.QUERY,
                "from": start_date.isoformat(),
                "to": end_date.isoformat(),
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": 100,
                "page": page,
            }
            try:
                resp = httpx.get(url, params=dict(params, apiKey=api_key), timeout=15)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                print(f"[NewsHistory] Fetch failed (page {page}): {e}")
                break

            articles = data.get("articles", [])
            if not articles:
                break

            for article in articles:
                published_str = article.get("publishedAt", "")
                if not published_str:
                    continue
                try:
                    # Parse date from ISO string: "2024-01-15T10:30:00Z"
                    art_date = date.fromisoformat(published_str[:10])
                except ValueError:
                    continue

                # Only cache articles within our range
                if not (start_date <= art_date <= end_date):
                    continue

                headline = article.get("title", "").strip()
                source = article.get("source", {}).get("name")
                url_val = article.get("url")

                if not headline or url_val in seen_urls:
                    continue
                seen_urls.add(url_val)

                cache.cache_headline(art_date, headline, source, url_val)
                fetched_dates.add(art_date)

            # NewsAPI max 100 results per page, 100 pages on free tier
            if len(articles) < 100:
                break
            page += 1

        return len(fetched_dates)

    def get_headlines(self, bar_date: date) -> list[dict]:
        """
        Return cached headlines for a specific date.

        Returns list of dicts with keys: headline, source, url.
        """
        return cache.get_headlines(bar_date)
