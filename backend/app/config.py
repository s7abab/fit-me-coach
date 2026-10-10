from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    database_url: str
    llm_api_key: str
    llm_base_url: str
    llm_model: str = "openai.gpt-oss-120b"
    warmup_models: bool = True
    cors_origins: list[str] = ["http://localhost:3000"]

    # Signs the short-lived token the Next.js server sends with every request. Same value as API_JWT_SECRET in frontend/.env.
    api_jwt_secret: str
    # Fernet key that encrypts Google refresh tokens before they are stored
    token_encryption_key: str
    # The same Google OAuth client the frontend signs in with: needed to refresh access tokens
    google_client_id: str
    google_client_secret: str

settings = Settings()
