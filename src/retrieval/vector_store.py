"""程序说明：封装 ChromaDB 持久化向量索引、维度校验与自动重建逻辑。"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, cast

import chromadb

from src.ai.embedding import BaseEmbeddingClient, DeterministicEmbeddingClient
from src.common.errors import ValidationAppError
from src.db.repositories import DocumentRepository
from src.retrieval.scope import normalize_knowledge_base_scope


class VectorStore:
    """ChromaDB 向量集合封装。"""

    def __init__(
        self,
        persist_directory,
        collection_name: str = "knowledge_chunks",
        embedding_client: BaseEmbeddingClient | None = None,
        sqlite_db_path=None,
        auto_repair_dimension_mismatch: bool = False,
        embedding_model: str = "deterministic-v1",
        index_version: str = "retrieval-v2",
    ) -> None:
        self.persist_directory = str(persist_directory)
        self.collection_name = collection_name
        self.embedding = embedding_client or DeterministicEmbeddingClient()
        self.sqlite_db_path = str(sqlite_db_path) if sqlite_db_path is not None else None
        self.auto_repair_dimension_mismatch = auto_repair_dimension_mismatch
        self.embedding_model = str(embedding_model or "unknown")
        self.index_version = str(index_version or "retrieval-v2")
        self.embedding_dimension = 0
        self.last_repair_summary: dict | None = None
        self._initialize_collection()
        try:
            self._validate_embedding_dimension()
        except ValidationAppError as exc:
            if not self._should_auto_repair_dimension_mismatch(exc):
                raise
            self._repair_dimension_mismatch(exc)

    def _initialize_collection(self) -> None:
        """初始化 Chroma 客户端与集合，并在旧索引格式不兼容时尝试自修复。"""

        try:
            self.client = chromadb.PersistentClient(path=self.persist_directory)
            self.collection = self.client.get_or_create_collection(name=self.collection_name)
        except Exception as exc:  # noqa: BLE001
            if not self._should_auto_repair_legacy_index(exc):
                raise
            self._repair_legacy_index(exc)

    def _should_auto_repair_legacy_index(self, exc: Exception) -> bool:
        """判断是否命中了可自动修复的旧版 Chroma 索引格式异常。"""

        message = str(exc)
        return bool(
            self.auto_repair_dimension_mismatch
            and self.sqlite_db_path
            and (
                (isinstance(exc, KeyError) and message.strip("'") == "_type")
                or "_type" in message
                or "configuration" in message.lower()
            )
        )

    def _repair_legacy_index(self, exc: Exception) -> None:
        """旧版 Chroma 集合元数据不兼容时，重建索引目录并从 SQLite 回填。"""

        persist_path = Path(self.persist_directory)
        backup_path = persist_path.with_name(f"{persist_path.name}_legacy_backup")
        if backup_path.exists():
            if backup_path.is_dir():
                shutil.rmtree(backup_path)
            else:
                backup_path.unlink()
        if persist_path.exists():
            shutil.move(str(persist_path), str(backup_path))
        persist_path.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=self.persist_directory)
        self.collection = self.client.get_or_create_collection(name=self.collection_name)
        repaired_docs, repaired_chunks = self.rebuild_from_sqlite()
        self.last_repair_summary = {
            "repaired": True,
            "repair_reason": "legacy_collection_config",
            "repaired_docs": repaired_docs,
            "repaired_chunks": repaired_chunks,
            "persist_directory": self.persist_directory,
            "legacy_backup_path": str(backup_path),
            "repair_error": str(exc),
        }

    def _validate_embedding_dimension(self) -> None:
        """启动时校验当前 embedding 维度与现有集合维度是否一致。"""

        current_dimension = self._infer_current_embedding_dimension()
        self.embedding_dimension = current_dimension
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

    def close(self) -> None:
        """显式释放 Chroma 客户端，避免 Windows 持有索引目录句柄。"""

        close_client = getattr(self.client, "close", None)
        if callable(close_client):
            close_client()

    def rebuild_from_sqlite(self, *, page_size: int = 100) -> tuple[int, int]:
        """基于 SQLite 已存储的 chunks 重建整个向量集合。"""

        if not self.sqlite_db_path:
            raise ValidationAppError(
                "缺少 sqlite_db_path，无法自动重建向量集合",
                details={"persist_directory": self.persist_directory},
            )

        repository = DocumentRepository(Path(self.sqlite_db_path))
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
                knowledge_base_id = str(document.get("knowledge_base_id") or "")
                # chunks 表不重复存知识库 ID，全量重建时必须从 documents 继承。
                enriched_chunks = [
                    {**item, "knowledge_base_id": knowledge_base_id}
                    for item in chunk_items
                ]
                self.upsert_chunks(enriched_chunks)
                repaired_docs += 1
                repaired_chunks += len(enriched_chunks)
            if page * page_size >= total:
                break
            page += 1
        return repaired_docs, repaired_chunks

    def upsert_chunks(self, items: list[dict], *, batch_size: int = 8, progress_callback=None) -> None:
        """批量写入 chunk 向量记录。H7 修复：metadata 中增加 knowledge_base_id。"""

        if not items:
            return

        total = len(items)
        for start in range(0, total, batch_size):
            batch = items[start : start + batch_size]
            documents = [item["content"] for item in batch]
            metadatas = []
            for item in batch:
                metadata = {
                    "doc_uid": item["doc_uid"],
                    "chunk_id": item["chunk_id"],
                    "source_span": item.get("source_span") or "",
                    "heading_path": item.get("heading_path") or "",
                    "source_anchor": item.get("source_anchor") or "",
                    "chunk_type": item.get("chunk_type") or "",
                    "content_hash": item.get("content_hash") or "",
                    # H7 修复：写入知识库 ID，支持向量检索按知识库过滤
                    "knowledge_base_id": item.get("knowledge_base_id") or "",
                    "embedding_model": self.embedding_model,
                    "embedding_dimension": self.embedding_dimension,
                    "index_version": self.index_version,
                }
                for trace_key in ("source_start_line", "source_end_line", "page_no"):
                    if item.get(trace_key) is not None:
                        metadata[trace_key] = int(item[trace_key])
                metadatas.append(metadata)
            self.collection.upsert(
                ids=[item["chunk_id"] for item in batch],
                documents=documents,
                metadatas=cast(Any, metadatas),
                embeddings=cast(Any, self.embedding.embed_texts(documents)),
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
        ids = self._to_sequence(result.get("ids"))
        if ids and isinstance(ids[0], list):
            return sum(len(self._to_sequence(item)) for item in ids)
        return len(ids)

    def inspect_index(self) -> dict:
        """汇总向量数量、归属和必填模型元数据。"""

        try:
            snapshot = self.collection.get(include=["metadatas"])
        except Exception as exc:  # noqa: BLE001
            raise ValidationAppError(
                "读取向量索引元数据失败",
                details={"collection_name": self.collection_name, "reason": str(exc)},
            ) from exc

        ids = self._to_sequence(snapshot.get("ids"))
        metadatas = self._to_sequence(snapshot.get("metadatas"))
        if ids and isinstance(ids[0], list):
            ids = [item for group in ids for item in self._to_sequence(group)]
        if metadatas and isinstance(metadatas[0], list):
            metadatas = [item for group in metadatas for item in self._to_sequence(group)]

        required_fields = (
            "chunk_id",
            "doc_uid",
            "knowledge_base_id",
            "embedding_model",
            "embedding_dimension",
            "index_version",
        )
        by_knowledge_base: dict[str, int] = {}
        by_document: dict[str, int] = {}
        models: set[str] = set()
        dimensions: set[int] = set()
        versions: set[str] = set()
        missing_metadata_count = 0
        for raw_metadata in metadatas:
            metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
            if any(metadata.get(field) in (None, "") for field in required_fields):
                missing_metadata_count += 1
            knowledge_base_id = str(metadata.get("knowledge_base_id") or "")
            doc_uid = str(metadata.get("doc_uid") or "")
            if knowledge_base_id:
                by_knowledge_base[knowledge_base_id] = by_knowledge_base.get(knowledge_base_id, 0) + 1
            if doc_uid:
                by_document[doc_uid] = by_document.get(doc_uid, 0) + 1
            if metadata.get("embedding_model"):
                models.add(str(metadata["embedding_model"]))
            if metadata.get("embedding_dimension") not in (None, ""):
                dimensions.add(int(metadata["embedding_dimension"]))
            if metadata.get("index_version"):
                versions.add(str(metadata["index_version"]))
        missing_metadata_count += max(len(ids) - len(metadatas), 0)
        return {
            "total_count": len(ids),
            "by_knowledge_base": by_knowledge_base,
            "by_document": by_document,
            "missing_metadata_count": missing_metadata_count,
            "embedding_models": sorted(models),
            "embedding_dimensions": sorted(dimensions),
            "index_versions": sorted(versions),
        }

    def query(
        self,
        query_text: str,
        top_k: int = 5,
        doc_uid: str | None = None,
        knowledge_base_id: str | None = None,
        knowledge_base_ids: list[str] | tuple[str, ...] | None = None,
    ) -> list[dict]:
        """执行向量检索，支持单知识库或多知识库范围。"""

        knowledge_base_scope = normalize_knowledge_base_scope(knowledge_base_id, knowledge_base_ids)
        if knowledge_base_scope == ():
            return []

        query_kwargs = {
            "query_embeddings": self.embedding.embed_texts([query_text]),
            "n_results": top_k,
            "include": ["documents", "metadatas", "distances"],
        }
        # 文档范围和知识库范围同时存在时，使用 Chroma 的 $and 组合。
        where_conditions: dict[str, object] = {}
        if doc_uid:
            where_conditions["doc_uid"] = doc_uid
        if knowledge_base_scope:
            where_conditions["knowledge_base_id"] = (
                knowledge_base_scope[0]
                if len(knowledge_base_scope) == 1
                else {"$in": list(knowledge_base_scope)}
            )
        if len(where_conditions) == 1:
            query_kwargs["where"] = where_conditions
        elif len(where_conditions) > 1:
            query_kwargs["where"] = {"$and": [{k: v} for k, v in where_conditions.items()]}

        query_collection = cast(Any, self.collection.query)
        result = query_collection(**query_kwargs)

        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]

        items: list[dict] = []
        for document, metadata, distance in zip(documents, metadatas, distances):
            items.append(
                {
                    "chunk_id": metadata.get("chunk_id"),
                    "doc_uid": metadata.get("doc_uid"),
                    "source_span": metadata.get("source_span"),
                    "heading_path": metadata.get("heading_path"),
                    "source_start_line": metadata.get("source_start_line"),
                    "source_end_line": metadata.get("source_end_line"),
                    "page_no": metadata.get("page_no"),
                    "source_anchor": metadata.get("source_anchor"),
                    "chunk_type": metadata.get("chunk_type"),
                    "content_hash": metadata.get("content_hash"),
                    "content": document,
                    "score": 1 - float(distance),
                }
            )
        return items
