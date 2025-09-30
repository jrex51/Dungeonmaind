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

    #results = vectorstore.similarity_search(query, k=top_k)
    results = vectorstore.similarity_search(
        query,
        k=top_k,
        filter={"source": source_db}
    )

    for i, doc in enumerate(results):
        print(f"Result {i + 1}: {doc.page_content}")



    return results


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