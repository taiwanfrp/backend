from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    db_url: str = ""
    db_mysql_ssl: bool = False
    redis_url: str = ""

    db_type: str = "mysql"
    
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

    @model_validator(mode="after")
    def set_db_type(self):
        if not self.db_url:
            raise ValueError("DB_URL is required")

        if self.db_url.startswith("mysql://") or self.db_url.startswith("mysql+"):
            self.db_type = "mysql"
        elif self.db_url.startswith("postgresql://") or self.db_url.startswith("postgresql+"):
            self.db_type = "postgresql"
        else:
            raise ValueError("DB_URL must use mysql or postgresql")

        return self
    
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True)

settings = Settings()