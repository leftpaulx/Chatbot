from pydantic_settings import BaseSettings



class Settings(BaseSettings):
    
    SNOWFLAKE_ACCOUNT: str
    SNOWFLAKE_PROJECT_USER: str
    PRIVATE_USER_KEY: str # PEM string

    # Timeouts & limits
    SQL_TIMEOUT_SEC: int = 30
    MAX_CONCURRENCY: int = 8 # Max concurrent requests should align with snowflake concurrency limit


    class Config:
        env_file = '.env'
        case_sensitive = True


settings = Settings()
