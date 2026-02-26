from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openai_api_key: str = ""
    youtube_url: str = ""

    # Models
    whisper_model: str = "whisper-1"
    classifier_model: str = "gpt-5-nano"
    verifier_model: str = "gpt-5.2"
    embedding_model: str = "text-embedding-3-small"

    # Stream
    chunk_duration: int = 10  # seconds
    ffmpeg_path: str = ""  # auto-detect if empty
    youtube_cookies_file: str = ""  # path to cookies.txt for bot bypass

    # Server
    host: str = "0.0.0.0"
    port: int = 8001
    log_level: str = "INFO"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
