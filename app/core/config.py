from pydantic_settings import BaseSettings


class Settings(BaseSettings):

    SNOWFLAKE_ACCOUNT: str
    SNOWFLAKE_PROJECT_USER: str
    PRIVATE_USER_KEY: str  # base64-encoded PEM private key

    # API key – the widget must send Authorization: Bearer <API_KEY>
    API_KEY: str

    # Cortex Agent Object path (tools, model, instructions configured on the object)
    AGENT_PATH: str = "/api/v2/databases/OB_AI/schemas/CHATBOT/agents/PROFITABILITY_AGENT:run"

    # CORS – comma-separated origins, or "*" for dev
    ALLOWED_ORIGINS: str = "*"

    # Timeouts & limits
    AGENT_TIMEOUT_SEC: int = 300
    MAX_CONCURRENCY: int = 8
    RATE_LIMIT_RPM: int = 30

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "text"  # "text" for human-readable, "json" for machine-parseable

    class Config:
        env_file = '.env'
        case_sensitive = True


settings = Settings()
