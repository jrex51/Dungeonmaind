from pydantic import BaseModel
from typing import List, Dict

class FolderContent(BaseModel):
    folders: List[str]
    files: List[str]

FolderStructure = Dict[str, FolderContent]

class FileContentResponse(BaseModel):
    content: str