from fastapi import HTTPException, status
import json
import os
import shutil
from app.core.config import settings


BASE_DIR = os.path.join(settings.backend_root_path, "data", "SavedSessions")


def delete_folder(folder: str) -> None:
    folder_path = os.path.join(BASE_DIR, folder)

    if not os.path.exists(folder_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Folder '{folder}' does not exist."
        )

    if not os.path.isdir(folder_path):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"'{folder}' is not a directory."
        )

    try:
        shutil.rmtree(folder_path)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete folder '{folder}': {str(e)}"
        )
