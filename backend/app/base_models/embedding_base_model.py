from pydantic import BaseModel, Field
from typing import List


class EmbeddRequest(BaseModel):
    input_string: str = Field(..., description="Text to be embedded")


class EmbeddResponse(BaseModel):
    markdown_texts: List[str]


class EmbeddingSearch(BaseModel):
    input_string: str = Field(..., description="Search string for embedding search")
