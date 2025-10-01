from app.core.config import settings
from langchain_community.embeddings import SentenceTransformerEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
import os
import shutil


def embedding_search(query: str, source=False, persist_directory=settings.chroma_db_path, top_k=2):
    if source:
        source_db = "rulebook"
    else:
        source_db = "transcriptions"

    embedding_model = SentenceTransformerEmbeddings(
        model_name="all-MiniLM-L6-v2"
    )

    vectorstore = Chroma(
        persist_directory=persist_directory,
        embedding_function=embedding_model
    )

    #results = vectorstore.similarity_search(query, k=top_k)
    results = vectorstore.similarity_search(
        query,
        k=top_k,
        filter={"source": source_db}
    )

    for i, doc in enumerate(results):
        print(f"Result {i + 1}: {doc.page_content}")

    return results

def embedd_transcriptions(embedding_text: list, persist_directory=settings.chroma_db_path):
    # Load embedding model locally
    embedding_model = SentenceTransformerEmbeddings(
        model_name="all-MiniLM-L6-v2"
    )

    documents = [
        Document(
            page_content=text,
            metadata={"source": "transcriptions"}
        )
        for i, text in enumerate(embedding_text)
    ]

    # Loads the chroma db vectorstore if already found under given path, otherwise creates it from scratch
    if os.path.exists(os.path.join(persist_directory, "chroma.sqlite3")):
        print("found db under " + persist_directory)
        vectorstore = Chroma(
            persist_directory=persist_directory,
            embedding_function=embedding_model
        )
        vectorstore.add_documents(documents)
    else:
        print("No database exists, creating a new database...")
        vectorstore = Chroma.from_documents(
            documents=documents,
            embedding=embedding_model,
            persist_directory=persist_directory
        )

    # From Chromadb => 4 on, this should be done automatically
    # vectorstore.persist()

    print(f"Saved {len(documents)} documents to Chroma at '{persist_directory}'")

def embedd_rulebook(embedding_text: list, txt_paths: dict, persist_directory =settings.chroma_db_path):
    """
    embedding_text: list of text content
    txt_paths: dict mapping index in embedding_text -> absolute txt path
    """
    embedding_model = SentenceTransformerEmbeddings(model_name="all-MiniLM-L6-v2")

    documents = []
    for text, txt_abs_path in zip(embedding_text, txt_paths):
        folder_name = os.path.basename(os.path.dirname(txt_abs_path))
        filename = os.path.basename(txt_abs_path)

        rel_path_with_prefix = os.path.join("./data/rulebook", folder_name, filename)
        #print(rel_path_with_prefix.replace("\\", "/"))

        doc = Document(
            page_content=text,
            metadata={
                "source": "rulebook",
                "player_id": "none",
                "session_id": "none",
                "path": rel_path_with_prefix.replace("\\", "/")
            }
        )
        documents.append(doc)

        # Loads the chroma db vectorstore if already found under given path, otherwise creates it from scratch
    if os.path.exists(os.path.join(persist_directory, "chroma.sqlite3")):
        print("found db under " + persist_directory)
        vectorstore = Chroma(
            persist_directory=persist_directory,
            embedding_function=embedding_model
        )
        vectorstore.add_documents(documents)
    else:
        print("No database exists, creating a new database...")
        vectorstore = Chroma.from_documents(
            documents=documents,
            embedding=embedding_model,
            persist_directory=persist_directory
        )

    print(f"Saved {len(documents)} documents to Chroma at '{persist_directory}'")

def read_text_files(rulebook_folder=None):
    if rulebook_folder is None:
        rulebook_folder = os.path.join(settings.backend_root_path, "data", "rulebook")

    texts = []
    txt_paths = []  # maps index in texts -> txt file path

    for subdir, dirs, files in os.walk(rulebook_folder):
        for file in files:
            if file.endswith(".txt"):
                txt_path = os.path.join(subdir, file)
                with open(txt_path, "r", encoding="utf-8") as f:
                    content = f.read()
                texts.append(content)
                txt_paths.append(txt_path.replace("\\", "/"))  # index -> txt path

    return texts, txt_paths

def delete_chromadb(persist_directory=settings.chroma_db_path):
    if os.path.exists(persist_directory):
        shutil.rmtree(persist_directory)
        print(f"Chroma DB at '{persist_directory}' has been deleted.")
    else:
        print("Chroma DB directory does not exist.")

def print_all_chromadb_entries(persist_directory=settings.chroma_db_path):
    embedding_model = SentenceTransformerEmbeddings(
        model_name="all-MiniLM-L6-v2"
    )

    if not os.path.exists(os.path.join(persist_directory, "chroma.sqlite3")):
        print("No Chroma DB found at", persist_directory)
        return

    vectorstore = Chroma(
        persist_directory=persist_directory,
        embedding_function=embedding_model
    )
    entries = vectorstore.get(ids=None)

    for i, doc in enumerate(entries['documents']):
        print(f"Entry {i + 1}")
        print(f"Document: {doc}")
        print(f"Metadata: {entries['metadatas'][i]}")
        print(f"ID: {entries['ids'][i]}")
        print("-" * 40)