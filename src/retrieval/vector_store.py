"""程序说明：封装 ChromaDB 持久化向量索引、维度校验与自动重建逻辑。"""

from __future__ import annotations

import chromadb

from src.ai.embedding import BaseEmbeddingClient, DeterministicEmbeddingClient
from src.common.errors import ValidationAppError
from src.db.repositories import DocumentRepository


class VectorStore:
    """ChromaDB 向量集合封装。"""

    def __init__(
        self,
        persist_directory,
        collection_name: str = "knowledge_chunks",
        embedding_client: BaseEmbeddingClient | None = None,
        sqlite_db_path=None,
        auto_repair_dimension_mismatch: bool = False,
    ) -> None:
        self.persist_directory = str(persist_directory)
        self.collection_name = collection_name
        self.embedding = embedding_client or DeterministicEmbeddingClient()
        self.sqlite_db_path = str(sqlite_db_path) if sqlite_db_path is not None else None
        self.auto_repair_dimension_mismatch = auto_repair_dimension_mismatch
        self.client = chromadb.PersistentClient(path=str(persist_directory))
        self.collection = self.client.get_or_create_collection(name=collection_name)
        try:
            self._validate_embedding_dimension()
        except ValidationAppError as exc:
            if not self._should_auto_repair_dimension_mismatch(exc):
                raise
            self._repair_dimension_mismatch(exc)

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

    def _should_auto_repair_dimension_mismatch(self, exc: ValidationAppError) -> bool:
        """判断当前异常是否可自动重建。"""

        details = exc.details or {}
        return bool(
            self.auto_repair_dimension_mismatch
            and self.sqlite_db_path
            and details.get("stored_dimension") is not None
            and details.get("current_dimension") is not None
        )

    def _repair_dimension_mismatch(self, exc: ValidationAppError) -> None:
        """检测到维度不一致时，重建向量集合。"""

        try:
            self.reset_collection()
            repaired_docs, repaired_chunks = self.rebuild_from_sqlite()
            self._validate_embedding_dimension()
            self.last_repair_summary = {
                "repaired": True,
                "repaired_docs": repaired_docs,
                "repaired_chunks": repaired_chunks,
                "stored_dimension": (exc.details or {}).get("stored_dimension"),
                "current_dimension": (exc.details or {}).get("current_dimension"),
            }
        except Exception as repair_exc:  # noqa: BLE001
            raise ValidationAppError(
                "检测到向量维度不一致，但自动重建失败",
                details={
                    **(exc.details or {}),
                    "persist_directory": self.persist_directory,
                    "repair_error": str(repair_exc),
                    "recommended_action": "检查 Embedding 配置与网络后重启；如仍失败，可删除 index/chroma 后重新入库",
                },
            ) from repair_exc

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

    def reset_collection(self) -> None:
        """删除并重建当前向量集合。"""

        try:
            self.client.delete_collection(name=self.collection_name)
        except Exception:  # noqa: BLE001
            pass
        self.collection = self.client.get_or_create_collection(name=self.collection_name)

    def rebuild_from_sqlite(self, *, page_size: int = 100) -> tuple[int, int]:
        """基于 SQLite 已存储的 chunks 重建整个向量集合。"""

        if not self.sqlite_db_path:
            raise ValidationAppError(
                "缺少 sqlite_db_path，无法自动重建向量集合",
                details={"persist_directory": self.persist_directory},
            )

        repository = DocumentRepository(self.sqlite_db_path)
        repaired_docs = 0
        repaired_chunks = 0
        page = 1
        while True:
            documents, total = repository.list_documents(page=page, page_size=page_size)
            if not documents:
                break
            for document in documents:
                doc_uid = str(document["doc_uid"])
                chunk_items = repository.list_chunks_by_doc_uid(doc_uid)
                if not chunk_items:
                    continue
                self.upsert_chunks(chunk_items)
                repaired_docs += 1
                repaired_chunks += len(chunk_items)
            if page * page_size >= total:
                break
            page += 1
        return repaired_docs, repaired_chunks

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
