"""Single source of configuration, validated at startup (12-factor, env vars or .env)."""

from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    data_dir: Path = Path(".data")
    timezone: str = "America/Sao_Paulo"

    jwt_secret: SecretStr
    jwt_issuer: str = "getnet-agents"
    jwt_audience: str = "getnet-chat"
    jwt_default_ttl_seconds: int = 3600

    rate_limit_per_minute: int = 30
    rate_limit_global_per_minute: int = 300
    max_message_chars: int = 2000
    warm_knowledge_index: bool = True
    # Evaluation only: include tool outputs in /chat responses so the judge can check grounding.
    expose_tool_results: bool = False

    anthropic_api_key: SecretStr | None = None
    llm_model: str = "claude-sonnet-5-5"  # measured choice, see docs/adr/008
    llm_budget_usd: float = 10.0
    max_cost_per_chat_usd: float = 0.40

    # Human handoff notifications (signed with HMAC-SHA256 when a secret is set)
    operator_webhook_url: str | None = None
    merchant_webhook_url: str | None = None
    webhook_secret: SecretStr | None = None

    @field_validator("jwt_secret")
    @classmethod
    def _strong_secret(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError("JWT_SECRET must have at least 32 characters (run `make setup`).")
        return value

    @field_validator("anthropic_api_key", "webhook_secret")
    @classmethod
    def _empty_is_none(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and not value.get_secret_value().strip():
            return None
        return value

    @property
    def db_path(self) -> Path:
        return self.data_dir / "getnet.db"

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def llm_configured(self) -> bool:
        return self.anthropic_api_key is not None

    def now(self) -> datetime:
        return datetime.now(self.tz)

    def today(self) -> date:
        return self.now().date()


@lru_cache
def get_settings() -> Settings:
    return Settings()  # values come from the environment
