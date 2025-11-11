import os

def read_markdown_file(md_path: str) -> str:
    """
    Reads the raw text of a Markdown file given its path.
    """
    if not os.path.exists(md_path):
        raise FileNotFoundError(f"Markdown file not found: {md_path}")

    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()

    return content
