"""程序说明：封装 ChromaDB 持久化向量索引与查询逻辑。"""

from __future__ import annotations

import chromadb

from src.ai.embedding import BaseEmbeddingClient, DeterministicEmbeddingClient
from src.common.errors import ValidationAppError


class VectorStore:
    """ChromaDB 向量集合封装。"""

    def __init__(
        self,
        persist_directory,
        collection_name: str = "knowledge_chunks",
        embedding_client: BaseEmbeddingClient | None = None,
    ) -> None:
        self.persist_directory = str(persist_directory)
        self.collection_name = collection_name
        self.embedding = embedding_client or DeterministicEmbeddingClient()
        self.client = chromadb.PersistentClient(path=str(persist_directory))
        self.collection = self.client.get_or_create_collection(name=collection_name)
        self._validate_embedding_dimension()

    def _validate_embedding_dimension(self) -> None:
        """启动时校验当前 embedding 维度与现有集合维度是否一致。"""

        current_dimension = self._infer_current_embedding_dimension()
        stored_dimension = self._infer_stored_embedding_dimension()
        if stored_dimension is None or stored_dimension == current_dimension:
            return
        raise ValidationAppError(
            "当前 Embedding 维度与现有向量索引不一致，请删除旧的 Chroma 索引后重建",
            details={
                "collection_name": self.collection_name,
                "persist_directory": self.persist_directory,
                "stored_dimension": stored_dimension,
                "current_dimension": current_dimension,
                "recommended_action": "备份后删除 index/chroma，并重新执行向量重建或文档入库",
            },
        )

    def _infer_current_embedding_dimension(self) -> int:
        """探测当前 embedding 客户端返回的维度。"""

        vectors = self.embedding.embed_texts(["embedding-dimension-self-check"])
        if not vectors or not vectors[0]:
            raise ValidationAppError(
                "启动时无法探测当前 Embedding 维度",
                details={
                    "collection_name": self.collection_name,
                    "persist_directory": self.persist_directory,
                },
            )
        return len(vectors[0])

    def _infer_stored_embedding_dimension(self) -> int | None:
        """从现有集合中读取一条向量，探测已存储的维度。"""

        snapshot = self.collection.peek(limit=1)
        ids = self._to_sequence(snapshot.get("ids"))
        if not ids:
            return None

        embeddings = self._to_sequence(snapshot.get("embeddings"))
        first_embedding = self._get_first_embedding(embeddings)
        if first_embedding is not None:
            return len(first_embedding)

        detail = self.collection.get(ids=[ids[0]], include=["embeddings"])
        stored_embeddings = self._to_sequence(detail.get("embeddings"))
        first_stored_embedding = self._get_first_embedding(stored_embeddings)
        if first_stored_embedding is not None:
            return len(first_stored_embedding)

        raise ValidationAppError(
            "启动时无法读取现有向量索引维度，请检查 Chroma 索引是否完整",
            details={
                "collection_name": self.collection_name,
                "persist_directory": self.persist_directory,
                "sample_id": ids[0],
                "recommended_action": "备份后删除 index/chroma，并重新执行向量重建或文档入库",
            },
        )

    def _to_sequence(self, value) -> list:
        """将 Chroma 返回值转换为可安全判空的顺序结构。"""

        if value is None:
            return []
        if isinstance(value, list):
            return value
        if hasattr(value, "tolist"):
            converted = value.tolist()
            return converted if isinstance(converted, list) else [converted]
        try:
            return list(value)
        except TypeError:
            return [value]

    def _get_first_embedding(self, embeddings: list) -> list[float] | None:
        """安全读取第一条向量，兼容 list 与 ndarray 等结构。"""

        if not embeddings:
            return None
        first_embedding = embeddings[0]
        if first_embedding is None:
            return None
        if hasattr(first_embedding, "tolist"):
            first_embedding = first_embedding.tolist()
        if isinstance(first_embedding, list):
            return first_embedding if first_embedding else None
        try:
            converted = list(first_embedding)
        except TypeError:
            return None
        return converted if converted else None

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

    def count_by_doc_uid(self, doc_uid: str) -> int:
        """统计指定文档当前已写入的向量条数。"""

        if not doc_uid:
            return 0
        result = self.collection.get(
            where={"doc_uid": doc_uid},
            include=[],
        )
        return len(result.get("ids", []))

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
