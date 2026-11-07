from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GWENGIFT_",
        env_file=".env",
        extra="ignore",
    )

    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "sqlite:///./data/gwengift.db"
    telegram_bot_token: SecretStr | None = None
    dev_identity_enabled: bool = False
    init_data_max_age_seconds: int = Field(default=300, gt=0)
    starting_demo_balance: int = 10_000
    manual_data_max_age_hours: int = Field(default=24, gt=0)
    external_data_max_age_hours: int = Field(default=48, gt=0)
    market_discrepancy_threshold: Decimal = Field(default=Decimal("0.35"), ge=0, le=1)
    market_discrepancy_action: Literal["pause", "discount"] = "pause"
    discrepancy_liquidity_discount: Decimal = Field(default=Decimal("0.25"), ge=0, le=1)
    tg_gifts_daily_url: str = "https://tggifts.com/data/floors-daily.json"
    market_cache_path: Path = Path("./data/tg-gifts-cache.json")
    target_rtp: Decimal = Field(default=Decimal("0.90"), gt=0, le=1)
    minimum_rtp: Decimal = Field(default=Decimal("0.85"), gt=0, le=1)
    replacement_fee_rate: Decimal = Field(default=Decimal("0.05"), ge=0, le=1)
    minimum_operator_margin: Decimal = Decimal("0")
    minimum_worst_outcome_ratio: Decimal = Field(default=Decimal("0.20"), ge=0, le=1)
    minimum_recent_sales: int = Field(default=2, ge=0)
    maximum_liquidity_discount: Decimal = Field(default=Decimal("0.75"), ge=0, le=1)
    drand_minimum_delay_seconds: int = Field(default=6, gt=0)
    drand_acceptance_margin_seconds: int = Field(default=1, ge=0)
    drand_resolution_grace_seconds: int = Field(default=60, gt=0)
    draw_lease_grace_seconds: int = Field(default=30, gt=0)
    worker_poll_interval_seconds: float = Field(default=1, gt=0)
    frontend_dist_path: Path = Path("../frontend/dist")

    @model_validator(mode="after")
    def validate_production_credentials(self) -> "Settings":
        if self.environment == "production":
            if not self.telegram_bot_token or not self.telegram_bot_token.get_secret_value():
                raise ValueError("GWENGIFT_TELEGRAM_BOT_TOKEN is required in production")
            if self.dev_identity_enabled:
                raise ValueError("Development identity cannot be enabled in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
