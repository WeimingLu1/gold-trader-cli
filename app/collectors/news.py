"""News collector — supports NewsAPI.org with mock fallback."""
import httpx
from datetime import datetime, timezone, timedelta
from app.collectors.base import BaseCollector, CollectedData
from app.config import get_settings


class NewsCollector(BaseCollector):
    """
    Collects gold/macro-relevant news headlines via NewsAPI.org.
    Falls back to mock data if API is unavailable or key not set.
    """

    name = "news"

    GOLD_KEYWORDS = [
        "gold", "xauusd", "goldman sachs", "fed", "treasury",
        "inflation", "deflation", "dollar", "dxy", "risk-off",
        "safe haven", "central bank", "pbc", "ecb", "fomc",
        "nonfarm payrolls", "cpi", "ppi", "gdp", "xau",
    ]

    async def collect(self) -> list[CollectedData]:
        settings = get_settings()
        api_key = settings.news_api_key or ""
        now = datetime.now(timezone.utc)

        if api_key:
            articles = await self._fetch_news(api_key)
            if articles:
                return [
                    CollectedData(
                        source="newsapi",
                        symbol=None,
                        event_time=now,
                        available_time=now,
                        fetched_at=now,
                        raw_payload=article,
                        normalized_payload={
                            "headline": article.get("title", ""),
                            "is_gold_key_driver": self._is_gold_key(article.get("title", "")),
                            "sentiment_score": 0.0,
                        },
                    )
                    for article in articles
                ]

        return self._mock_data(now)

    async def _fetch_news(self, api_key: str) -> list[dict]:
        """Fetch gold/macro news from NewsAPI.org."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Search for gold and macro-related news
                query = "gold OR XAUUSD OR Fed OR inflation OR dollar OR treasury"
                url = (
                    "https://newsapi.org/v2/everything"
                    f"?q={query}&language=en&sortBy=publishedAt&pageSize=10&apiKey={api_key}"
                )
                response = await client.get(url)
                if response.status_code == 200:
                    data = response.json()
                    return data.get("articles", []) or []
                else:
                    print(f"[NewsAPI] 请求失败: {response.status_code} {response.text[:100]}")
        except Exception as e:
            print(f"[NewsAPI] 连接错误: {e}")
        return []

    def _is_gold_key(self, headline: str) -> bool:
        text = headline.lower()
        return any(kw in text for kw in self.GOLD_KEYWORDS)

    def _mock_data(self, now: datetime) -> list[CollectedData]:
        """Return mock news data."""
        mock_headlines = [
            {
                "title": "Fed holds rates steady, signals caution on inflation",
                "source": "Reuters",
            },
            {
                "title": "Gold hits 1-week high as dollar weakens",
                "source": "Bloomberg",
            },
            {
                "title": "China central bank raises gold reserves for 3rd month",
                "source": "CNBC",
            },
        ]
        return [
            CollectedData(
                source="newsapi_mock",
                symbol=None,
                event_time=now,
                available_time=now,
                fetched_at=now,
                raw_payload=article,
                normalized_payload={
                    "headline": article["title"],
                    "is_gold_key_driver": self._is_gold_key(article["title"]),
                    "sentiment_score": 0.0,
                },
            )
            for article in mock_headlines
        ]
