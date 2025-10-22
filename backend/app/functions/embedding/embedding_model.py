from app.core.config import settings
from langchain_community.embeddings import SentenceTransformerEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
import os
import shutil

def embedding_search(query: str, source=False, persist_directory=settings.chroma_db_path):
    if source:
        source_db = "rulebook"
    else:
        source_db = "transcriptions"

    embedding_model = SentenceTransformerEmbeddings(
        model_name=settings.embedding_model
    )

    vectorstore = Chroma(
        persist_directory=persist_directory,
        embedding_function=embedding_model
    )

    # If rulebook search is active only use rulebook embeddings
    if source_db == "rulebook":
        #results = vectorstore.similarity_search(query, k=top_k)
        results = vectorstore.similarity_search(
            query,
            k=settings.embedding_top_k,
            filter={"source": source_db}
        )
    # If LLM is asked use the transcriptions and the rulebook information
    else:
        # Here maybe just do one search where both rulebook and transcriptions are allowed, but if one has a very high
        # amount transcriptions, necessary rulebook entries might not be found if k is too low
        results_rulebook = vectorstore.similarity_search(
            query,
            k=2,
            filter={"source": "rulebook"}
        )
        results_transcriptions = vectorstore.similarity_search(
            query,
            k=settings.embedding_top_k,
            filter={"source": "transcriptions"}
        )

        results = results_rulebook + results_transcriptions


    for i, doc in enumerate(results):
        print(f"Result {i + 1}: {doc.page_content}")
        if source:
            print("Path:", doc.metadata.get("path"))

    return results


def embedd_transcriptions(embedding_text: list, player_id="none", persist_directory=settings.chroma_db_path):
    # Load embedding model locally
    embedding_model = SentenceTransformerEmbeddings(
        model_name=settings.embedding_model
    )

    documents = [
        Document(
            page_content=text,
            metadata={"source": "transcriptions",
                      "player_id": player_id,  # Update here later
                      "session_id": "none",  # Update here later
                      "path": "none"}
        )
        for i, text in enumerate(embedding_text)
    ]

    write_to_ChromaDB(persist_directory, documents, embedding_model)


def embedd_rulebook(embedding_text: list, txt_paths: dict, persist_directory=settings.chroma_db_path):
    """
    embedding_text: list of text content
    txt_paths: dict mapping index in embedding_text -> absolute txt path
    """
    embedding_model = SentenceTransformerEmbeddings(model_name=settings.embedding_model)

    documents = []
    for text, txt_abs_path in zip(embedding_text, txt_paths):
        md_abs_path = txt_abs_path.replace(".txt", ".md")
        folder_name = os.path.basename(os.path.dirname(md_abs_path))
        filename = os.path.basename(md_abs_path)

        rel_path_with_prefix = os.path.join("./data/markdowns", folder_name, filename)
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

    write_to_ChromaDB(persist_directory, documents, embedding_model)


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


def delete_transcription_embeddings(persist_directory=settings.chroma_db_path):
    # Load embedding model
    embedding_model = SentenceTransformerEmbeddings(
        model_name=settings.embedding_model
    )

    if not os.path.exists(os.path.join(persist_directory, "chroma.sqlite3")):
        print("No database found at:", persist_directory)
        return

    vectorstore = Chroma(
        persist_directory=persist_directory,
        embedding_function=embedding_model
    )

    collection = vectorstore._collection
    all_docs = collection.get(include=["metadatas"])

    ids_to_delete = [
        doc_id for doc_id, meta in zip(all_docs["ids"], all_docs["metadatas"])
        if meta.get("source") == "transcriptions"
    ]

    if not ids_to_delete:
        print("No transcriptions in database found.")
        return

    collection.delete(ids=ids_to_delete)
    print(f"Deleted {len(ids_to_delete)} documents with source='transcriptions'")


# Not finished yet!
def reembed_chroma_entries(new_model: str, persist_directory=settings.chroma_db_path):
    old_model = settings.embedding_model

    if old_model == new_model:
        return

    old_embedding_model = SentenceTransformerEmbeddings(model_name=old_model)
    new_embedding_model = SentenceTransformerEmbeddings(model_name=new_model)

    if not os.path.exists(os.path.join(persist_directory, "chroma.sqlite3")):
        print("No database found at:", persist_directory)
        return

    vectorstore = Chroma(
        persist_directory=persist_directory,
        embedding_function=old_embedding_model
    )

    collection = vectorstore._collection
    all_data = collection.get(include=["metadatas", "documents"])

    texts = all_data["documents"]
    metadatas = all_data["metadatas"]
    ids = all_data["ids"]

    if not texts:
        print("No documents found in the database.")
        return

    print(f"Found {len(texts)} documents. Re-embedding with {new_model}...")

    new_embeddings = new_embedding_model.embed_documents(texts)

    collection.delete(ids=ids)

    collection.add(
        ids=ids, documents=texts, metadatas=metadatas, embeddings=new_embeddings
    )

    print(f"Re-embedded {len(texts)} documents with {new_model}.")

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



def write_to_ChromaDB(persist_directory, documents, embedding_model):
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