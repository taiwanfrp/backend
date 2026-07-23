from pydantic import BaseModel, ConfigDict
from datetime import datetime


class PermissionResponse(BaseModel):
    id: int
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
