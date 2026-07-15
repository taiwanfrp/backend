from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    detail: str | dict = Field(..., description="錯誤詳細資訊")
