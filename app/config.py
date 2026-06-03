from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    db_type: str = "mysql"
    db_host: str = "localhost"
    db_port: int = 3306
    db_user: str = "root"
    db_password: str = "password"
    db_name: str = "mydatabase"
    
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_user: str = ""
    redis_password: str = ""
    redis_db: int = 0
    
    discord_client_id: str = ""
    discord_client_secret: str = ""
    discord_redirect_uri: str = ""
    discord_oauth2_scope: str = "identify+email+guilds"
    
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True)

settings = Settings()