import os
from app.core.config import settings
from fastapi import APIRouter, HTTPException
from app.base_models.rulebook import FolderStructure, FolderContent, FileContentResponse
from app.functions.embedding.markdown_reader import read_markdown_file

router = APIRouter()
#BASE_DIR = "./data/markdowns"
BASE_DIR = os.path.join(settings.backend_root_path, "data", "markdowns")

@router.get("/folders", response_model=FolderStructure)
async def get_folders():
    folder_dict = {}
    for root, dirs, files in os.walk(BASE_DIR):
        rel_root = os.path.relpath(root, BASE_DIR)
        if rel_root == ".":
            rel_root = ""
        folder_dict[rel_root] = FolderContent(
            folders=dirs,
            files=[f for f in files if f.endswith(".md")]
        )
    print(folder_dict)
    return folder_dict



@router.get("/file", response_model=FileContentResponse)
async def get_file(path: str):
    abs_path = os.path.join(BASE_DIR, path)
    if not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail="Markdown file not found")

    return FileContentResponse(content=read_markdown_file(abs_path))
