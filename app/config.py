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
    
    cookie_auth_name: str = "auth"
    cookie_auth_max_age: int = 604800  # 7天
    cookie_auth_login_state_name: str = "oauth_state"
    cookie_auth_login_state_max_age: int = 300  # 5分鐘
    cookie_2fa_required_name: str = "2fa_required"
    cookie_2fa_max_age: int = 300  # 5分鐘
    cookie_httponly: bool = True
    cookie_max_age: int = 604800  # 7天, 用於未指定 max_age 的 cookie
    cookie_path: str = "/"
    cookie_samesite: str = "lax"
    cookie_secure: bool = True
    cookie_domain: str = "localhost"
    
    discord_client_id: str = ""
    discord_client_secret: str = ""
    discord_redirect_uri: str = ""
    discord_oauth2_scope: str = "identify+email+guilds"
    
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True)

settings = Settings()