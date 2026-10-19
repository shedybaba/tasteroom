from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    # .env lives at the repo root locally; on the host these come from real env vars.
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env", extra="ignore", populate_by_name=True
    )

    qloo_api_key: str = ""
    # The local .env names this variable Qloo_Hackathon_API_Server_URL; accept both.
    qloo_base_url: str = Field(
        default="https://hackathon.api.qloo.com",
        validation_alias=AliasChoices("QLOO_BASE_URL", "Qloo_Hackathon_API_Server_URL"),
    )
    openai_api_key: str = ""
    # Defaults are the cheap / balanced models listed in OpenAI's model docs (Oct 2026). Override in .env.
    openai_model_fast: str = "gpt-6-luna"
    openai_model_smart: str = "gpt-6.1-sol"
    app_env: str = "development"
    rate_limit_plan: str = "5/hour"
    rate_limit_suggest: str = "60/minute"  # autocomplete + ideas: cheap and cached, but protect the Qloo key
    agent_disabled: bool = False

    @property
    def qloo_live(self) -> bool:
        return bool(self.qloo_api_key)

    @property
    def llm_live(self) -> bool:
        return bool(self.openai_api_key)


settings = Settings()
