from typing import Any, Optional
import uuid

import chromadb
from loguru import logger
from sentence_transformers import SentenceTransformer

import config

_chroma_client: Optional[chromadb.Client] = None
_collection: Optional[chromadb.Collection] = None
_embedder: Optional[SentenceTransformer] = None

def _get_embedder() -> SentenceTransformer:
    global _embedder
    if _embedder is None:
        logger.info(f"Loading embedding model: {config.EMBEDDING_MODEL}")
        _embedder = SentenceTransformer(config.EMBEDDING_MODEL)
    return _embedder

def _get_collection() -> chromadb.Collection:
    global _chroma_client, _collection
    if _collection is None:
        _chroma_client = chromadb.PersistentClient(path=config.CHROMA_PERSIST_DIR)
        _collection = _chroma_client.get_or_create_collection(
            name=config.CHROMA_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
            embedding_function=None,
        )
        logger.info(
            f"ChromaDB collection '{config.CHROMA_COLLECTION_NAME}' ready "
            f"({_collection.count()} docs)"
        )
    return _collection

def chunk_text(text: str, chunk_size: int = 400, overlap: int = 50) -> list[str]:
    words = text.split()
    chunks: list[str] = []
    step = max(1, chunk_size - overlap)
    for i in range(0, len(words), step):
        chunk = " ".join(words[i : i + chunk_size])
        if chunk:
            chunks.append(chunk)
    return chunks

def add_documents(
    texts: list[str],
    metadatas: list[dict[str, Any]],
    ids: Optional[list[str]] = None,
) -> list[str]:
    if not texts:
        return []

    collection = _get_collection()
    embedder = _get_embedder()

    doc_ids = ids or [str(uuid.uuid4()) for _ in texts]
    embeddings = embedder.encode(texts, show_progress_bar=False).tolist()

    collection.add(
        documents=texts,
        embeddings=embeddings,
        metadatas=metadatas,
        ids=doc_ids,
    )
    logger.info(f"Added {len(texts)} documents to ChromaDB")
    return doc_ids

def ingest_scraped_page(
    page: dict[str, Any],
    extra_metadata: Optional[dict[str, Any]] = None,
) -> list[str]:
    text = page.get("text", "")
    if not text or len(text) < 50:
        return []

    chunks = chunk_text(text)
    base_meta = {
        "source": page.get("url", "unknown"),
        "title": page.get("title", "")[:200],
    }
    if extra_metadata:
        base_meta.update(extra_metadata)

    metadatas = [base_meta.copy() for _ in chunks]
    return add_documents(chunks, metadatas)

def query(
    query_text: str,
    n_results: int = 5,
    where: Optional[dict] = None,
) -> list[dict[str, Any]]:
    collection = _get_collection()
    embedder = _get_embedder()

    query_embedding = embedder.encode([query_text], show_progress_bar=False).tolist()

    kwargs: dict[str, Any] = {
        "query_embeddings": query_embedding,
        "n_results": min(n_results, max(1, collection.count())),
        "include": ["documents", "metadatas", "distances"],
    }
    if where:
        kwargs["where"] = where

    results = collection.query(**kwargs)

    output: list[dict[str, Any]] = []
    for i, doc_id in enumerate(results["ids"][0]):
        output.append(
            {
                "id": doc_id,
                "document": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "distance": results["distances"][0][i],
            }
        )
    return output

def collection_count() -> int:
    return _get_collection().count()
