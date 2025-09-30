from langchain_community.embeddings import SentenceTransformerEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
import os
import shutil


def embedd_text(embedding_text: list, persist_directory="./data/chroma_db"):
    # Load embedding model locally
    embedding_model = SentenceTransformerEmbeddings(
        model_name="all-MiniLM-L6-v2"
    )

    documents = [
        Document(
            page_content=text,
            metadata={"source": "transcriptions",
                      "player_id": "none", # Update here later
                      "session_id": "none", # Update here later
                      "path": "none"}
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
        print("ERROR: DATABASE NOT FOUND")
        vectorstore = Chroma.from_documents(
            documents=documents,
            embedding=embedding_model,
            persist_directory=persist_directory
        )

    # From Chromadb => 4 on, this should be done automatically
    # vectorstore.persist()

    print(f"Saved {len(documents)} documents to Chroma at '{persist_directory}'")

def embedding_search(query: str, source=False, persist_directory="./data/chroma_db", top_k=2):
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

    # If rulebook search is active only use rulebook embeddings
    if source_db == "rulebook":
        #results = vectorstore.similarity_search(query, k=top_k)
        results = vectorstore.similarity_search(
            query,
            k=top_k,
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
            k=top_k,
            filter={"source": "transcriptions"}
        )

        results = results_rulebook + results_transcriptions


    for i, doc in enumerate(results):
        print(f"Result {i + 1}: {doc.page_content}")
        if source:
            print("Path:", doc.metadata.get("path"))

    return results


def delete_transcription_embeddings(persist_directory="./data/chroma_db"):
    # Load embedding model
    embedding_model = SentenceTransformerEmbeddings(
        model_name="all-MiniLM-L6-v2"
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


def reembed_chroma_entries(persist_directory="./data/chroma_db",
                           old_model="all-MiniLM-L6-v2",
                           new_model="all-MiniLM-L6-v2"):

    if(old_model == new_model):
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

def delete_chromadb(persist_directory="./data/chroma_db"):
    if os.path.exists(persist_directory):
        shutil.rmtree(persist_directory)
        print(f"Chroma DB at '{persist_directory}' has been deleted.")
    else:
        print("Chroma DB directory does not exist.")

def print_all_chromadb_entries(persist_directory="./data/chroma_db"):
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