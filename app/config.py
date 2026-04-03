from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "sqlite:///./gold_trader.db"

    # LLM
    llm_model: str = "gpt-4o-mini"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_temperature: float = 0.3
    llm_max_tokens: int = 1024

    # Scheduling
    schedule_interval_hours: int = 4
    default_horizon_hours: int = 4

    # Logging
    log_level: str = "INFO"

    # Strategy
    weights_file: str = "config/weights.yaml"

    # Data sources (feature flags)
    enable_market_data: bool = True
    enable_rates: bool = True
    enable_news: bool = True
    enable_macro_calendar: bool = True
    enable_positioning: bool = True
    enable_etf_flows: bool = True

    # External API keys
    gold_api_key: str = ""
    fred_api_key: str = ""
    news_api_key: str = ""


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
