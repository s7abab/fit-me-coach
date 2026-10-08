from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    database_url: str
    llm_api_key: str
    llm_base_url: str
    llm_model: str = "openai.gpt-oss-120b"

settings = Settings()