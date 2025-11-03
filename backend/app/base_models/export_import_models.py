from pydantic import BaseModel, Field
from typing import List


class ExportRequest(BaseModel):
    session_name: str = Field(..., description="Name of the session to be saved")


class ImportRequest(BaseModel):
    session_name: str = Field(..., description="Name of the session to be loaded")


class Sessions(BaseModel):
    folders: List[str]
