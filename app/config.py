from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    db_url: str = Field(default="", validation_alias="DATABASE_URL")
    db_mysql_ssl: bool = Field(default=False, validation_alias="DATABASE_MYSQL_SSL")
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

    discord_client_id: str = ""
    discord_client_secret: str = ""
    discord_redirect_uri: str = ""
    discord_oauth2_scope: str = "identify+email+guilds"

    node_region: str = Field(default="unknown-region", validation_alias="REGION")
    pod_name: str = Field(default="", validation_alias="HOSTNAME")
    server_id: str = "unknown-server"

    @model_validator(mode="after")
    def set_db_type(self):
        if not self.db_url:
            raise ValueError("DATABASE_URL is required")

        if self.db_url.startswith("mysql://") or self.db_url.startswith("mysql+"):
            self.db_type = "mysql"
        elif self.db_url.startswith("postgresql://") or self.db_url.startswith(
            "postgresql+"
        ):
            self.db_type = "postgresql"
        else:
            raise ValueError("DATABASE_URL must use mysql or postgresql")

        return self

    @model_validator(mode="after")
    def format_server_id(self):
        if self.pod_name:
            parts = self.pod_name.split("-")
            if len(parts) >= 2:
                short_id = "-".join(parts[-2:])
                self.server_id = f"{self.node_region}-{short_id}"
            else:
                self.server_id = f"{self.node_region}-{self.pod_name}"
        else:
            self.server_id = f"{self.node_region}-unknown"

        return self

    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True)


settings = Settings()
