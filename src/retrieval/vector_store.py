"""程序说明：封装 ChromaDB 持久化向量索引与查询逻辑。"""

from __future__ import annotations

import chromadb

from src.ai.embedding import BaseEmbeddingClient, DeterministicEmbeddingClient


class VectorStore:
    """ChromaDB 向量集合封装。"""

    def __init__(
        self,
        persist_directory,
        collection_name: str = "knowledge_chunks",
        embedding_client: BaseEmbeddingClient | None = None,
    ) -> None:
        self.client = chromadb.PersistentClient(path=str(persist_directory))
        self.collection = self.client.get_or_create_collection(name=collection_name)
        self.embedding = embedding_client or DeterministicEmbeddingClient()

    def upsert_chunks(self, items: list[dict], *, batch_size: int = 8, progress_callback=None) -> None:
        """批量写入 chunk 向量记录。"""

        if not items:
            return

        total = len(items)
        for start in range(0, total, batch_size):
            batch = items[start : start + batch_size]
            documents = [item["content"] for item in batch]
            metadatas = [
                {
                    "doc_uid": item["doc_uid"],
                    "chunk_id": item["chunk_id"],
                    "source_span": item.get("source_span") or "",
                }
                for item in batch
            ]
            self.collection.upsert(
                ids=[item["chunk_id"] for item in batch],
                documents=documents,
                metadatas=metadatas,
                embeddings=self.embedding.embed_texts(documents),
            )
            if progress_callback:
                progress_callback(
                    {
                        "completed_chunks": min(start + len(batch), total),
                        "total_chunks": total,
                        "batch_size": len(batch),
                    }
                )

    def delete_by_doc_uid(self, doc_uid: str) -> None:
        """按文档标识删除旧向量。"""

        self.collection.delete(where={"doc_uid": doc_uid})

    def query(self, query_text: str, top_k: int = 5, doc_uid: str | None = None) -> list[dict]:
        """执行向量检索。"""

        query_kwargs = {
            "query_embeddings": self.embedding.embed_texts([query_text]),
            "n_results": top_k,
            "include": ["documents", "metadatas", "distances"],
        }
        if doc_uid:
            query_kwargs["where"] = {"doc_uid": doc_uid}

        result = self.collection.query(
            **query_kwargs,
        )

        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]

        items: list[dict] = []
        for document, metadata, distance in zip(documents, metadatas, distances):
            items.append(
                {
                    "chunk_id": metadata.get("chunk_id"),
                    "doc_uid": metadata.get("doc_uid"),
                    "source_span": metadata.get("source_span"),
                    "content": document,
                    "score": 1 - float(distance),
                }
            )
        return items
