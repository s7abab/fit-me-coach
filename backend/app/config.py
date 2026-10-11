from pathlib import Path
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    database_url: str
    llm_api_key: str
    llm_base_url: str
    llm_model: str = "openai.gpt-oss-120b"

    # Voyage AI: embeddings and reranking for guideline search
    voyage_api_key: str
    # Keys made in MongoDB Atlas use https://ai.mongodb.com/v1 instead
    voyage_base_url: str = "https://api.voyageai.com/v1"
    voyage_embed_model: str = "voyage-3.5"
    voyage_rerank_model: str = "rerank-3-lite"

    cors_origins: list[str] = ["http://localhost:3000"]

    # The address this API is reached at from the internet: the MCP server's OAuth links are built from it.
    # Render sets RENDER_EXTERNAL_URL by itself; set PUBLIC_URL when using a custom domain.
    public_url: str = Field("http://localhost:8000", validation_alias=AliasChoices("PUBLIC_URL", "RENDER_EXTERNAL_URL"))

    # Signs the short-lived token the Next.js server sends with every request. Same value as API_JWT_SECRET in frontend/.env.
    api_jwt_secret: str
    # Fernet key that encrypts Google refresh tokens before they are stored
    token_encryption_key: str
    # The same Google OAuth client the frontend signs in with: needed to refresh access tokens
    google_client_id: str
    google_client_secret: str

settings = Settings()
