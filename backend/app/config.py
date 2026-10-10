from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[1] / ".env" 
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE)

    database_url: str
    llm_api_key: str
    llm_base_url: str
    llm_model: str = "openai.gpt-oss-120b"
    demo_user_id: int = 1
    warmup_models: bool = True
    cors_origins: list[str] = ["http://localhost:3000"]

settings = Settings()