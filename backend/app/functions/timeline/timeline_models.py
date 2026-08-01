from pydantic import BaseModel, Field


class TimelineEvent(BaseModel):
    timestamp: float = Field(..., description="Event timestamp in seconds")
    title: str = Field(..., description="Short event title")
    description: str = Field(..., description="Full event description")