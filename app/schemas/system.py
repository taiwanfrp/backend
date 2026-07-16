from pydantic import BaseModel


class HealthCheckResponseModel(BaseModel):
    api: str
    version: str
    database: str
    redis: str
