"""Single source of configuration, validated at startup (12-factor, env vars or .env)."""

from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Self
from zoneinfo import ZoneInfo

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    data_dir: Path = Path(".data")
    # App state in Postgres (shared by replicas); unset = the local SQLite file (docs/adr/014)
    state_database_url: str | None = None
    # Rate limit counters in Redis (shared by replicas); unset = in-process buckets
    redis_url: str | None = None
    timezone: str = "America/Sao_Paulo"

    # Tokens from an external OIDC issuer, checked against its JWKS (the compose default).
    oidc_issuer: str | None = None
    oidc_audience: str = "getnet-chat"
    oidc_jwks_url: str | None = None  # unset = read from the issuer's discovery document
    # Local HS256 tokens, used only when OIDC_ISSUER is unset (offline tests, quick local run).
    jwt_secret: SecretStr | None = None
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
    verifier_model: str = "claude-haiku-5-5"  # final-answer verifier, see docs/adr/012
    verify_answers: bool = True
    llm_budget_usd: float = 10.0
    max_cost_per_chat_usd: float = 0.40

    # Human handoff notifications (signed with HMAC-SHA256 when a secret is set)
    operator_webhook_url: str | None = None
    merchant_webhook_url: str | None = None
    webhook_secret: SecretStr | None = None
    # Operator console link used in notifications, and how often overdue handoffs are checked.
    operator_console_url: str = "http://127.0.0.1:8000/operator"
    handoff_sweep_seconds: float = 30.0
    # Telegram channel for operators (app/hitl/telegram.py): bot token from BotFather and the
    # chat ids allowed to receive handoffs and send commands (comma-separated).
    telegram_bot_token: SecretStr | None = None
    telegram_operator_chat_ids: str = ""
    telegram_polling: bool = True  # read commands in this replica (enable in one replica only)

    @field_validator("jwt_secret")
    @classmethod
    def _strong_secret(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None or not value.get_secret_value():
            return None
        if len(value.get_secret_value()) < 32:
            raise ValueError("JWT_SECRET must have at least 32 characters (run `make setup`).")
        return value

    @field_validator("oidc_issuer", "oidc_jwks_url")
    @classmethod
    def _blank_url_is_none(cls, value: str | None) -> str | None:
        return (value.strip() or None) if value is not None else None

    @model_validator(mode="after")
    def _token_source(self) -> Self:
        if self.oidc_issuer is None and self.jwt_secret is None:
            raise ValueError("Set OIDC_ISSUER, or JWT_SECRET for local tokens (run `make setup`).")
        return self

    @field_validator("anthropic_api_key", "webhook_secret", "telegram_bot_token")
    @classmethod
    def _empty_is_none(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and not value.get_secret_value().strip():
            return None
        return value

    @property
    def telegram_chat_ids(self) -> frozenset[int]:
        return frozenset(
            int(x) for x in self.telegram_operator_chat_ids.replace(" ", "").split(",") if x
        )

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
