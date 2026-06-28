from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./dev.db"
    redis_url: str = "redis://localhost:6379"
    chroma_persist_dir: str = "./chroma_data"

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    minimax_api_key: str = ""
    minimax_base_url: str = "https://api.minimax.chat"
    glm_api_key: str = ""
    glm_base_url: str = "https://open.bigmodel.cn/api/paas"
    volcengine_api_key: str = Field(default="", alias="ARK_API_KEY")
    volcengine_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    hf_endpoint: str = ""

    default_llm_provider: str = "deepseek"
    jwt_secret: str = "change-me-in-production"
    max_upload_size_mb: int = 50
    cors_origins: str = "http://localhost:3000"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
