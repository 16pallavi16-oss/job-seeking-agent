from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/job_seeker_bot"

    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    SERPAPI_API_KEY: str = ""

    BACKEND_URL: str = "http://localhost:8000"
    UPLOAD_DIR: str = "./uploads"


settings = Settings()
