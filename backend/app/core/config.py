from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = (
        "postgresql+asyncpg://exam_review:exam-review-dev@localhost:5432/exam_review"
    )
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
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    auth_cookie_secure: bool = True
    max_upload_size_mb: int = 50
    max_archive_uncompressed_mb: int = 128
    s3_endpoint_url: str = "http://127.0.0.1:9000"
    s3_public_endpoint_url: str = "http://127.0.0.1:9000"
    s3_allow_insecure_http: bool = False
    s3_region: str = "us-east-1"
    s3_bucket: str = "exam-review-materials"
    s3_access_key_id: str = ""
    s3_secret_access_key: SecretStr = Field(default_factory=lambda: SecretStr(""))
    s3_presigned_url_ttl_seconds: int = 300
    s3_connect_timeout_seconds: int = 5
    s3_read_timeout_seconds: int = 30
    material_job_stale_seconds: int = 900
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
