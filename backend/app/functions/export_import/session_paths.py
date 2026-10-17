"""Constrain saved-session paths on both Windows and POSIX hosts."""

from pathlib import Path

from fastapi import HTTPException


def saved_path(root, *parts):
    """Join one campaign or a campaign/session pair of single components."""
    if not 1 <= len(parts) <= 2:
        raise HTTPException(400, "Expected a campaign or campaign/session path")
    root = Path(root).resolve()
    candidate = root
    for part in parts:
        # Reject Windows paths on Linux too, including drive-relative paths and
        # ADS names. Names must not add hierarchy below the session directory.
        if not part or "/" in part or "\\" in part or ":" in part or "\0" in part:
            raise HTTPException(400, "Invalid campaign/session path")
        if part in (".", "..") or part.endswith((" ", ".")):
            raise HTTPException(400, "Invalid campaign/session path")
        candidate /= part
        if candidate.is_symlink() or candidate.is_junction():
            raise HTTPException(400, "Saved session paths cannot contain links")
    resolved = candidate.resolve()
    if resolved == root or not resolved.is_relative_to(root):
        raise HTTPException(400, "Invalid campaign/session path")
    return resolved


def saved_deletion_path(root, target):
    """Deletion accepts exactly 'campaign' or 'campaign/session'."""
    return saved_path(root, *target.split("/"))


def validate_session_tree(folder):
    # Existing file links could otherwise redirect JSON writes or copytree
    # outside the configured directory, even with safe campaign/session names.
    folder = Path(folder)
    if folder.is_symlink() or folder.is_junction():
        raise HTTPException(400, "Saved sessions cannot contain links")
    if folder.exists():
        for path in folder.rglob("*"):
            if path.is_symlink() or path.is_junction():
                raise HTTPException(400, "Saved sessions cannot contain links")
