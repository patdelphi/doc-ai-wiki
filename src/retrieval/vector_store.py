"""程序说明：提供稳定的本地向量索引，避免 Windows 下 Chroma 原生库崩溃。"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import numpy as np

from src.ai.embedding import BaseEmbeddingClient, DeterministicEmbeddingClient
from src.common.errors import ValidationAppError
from src.db.repositories import DocumentRepository
from src.retrieval.scope import normalize_knowledge_base_scope


class VectorStore:
    """使用 NumPy 精确余弦相似度的持久化向量存储。

    ``CHROMA_PERSIST_DIR`` 配置名保留，以兼容已有部署配置；目录内容改为
    单个原子替换的 ``vectors.npz`` 文件，避免 Chroma/HNSW 在 Windows 上的
    native access violation 以及多文件半写入状态。
    """

    _FILE_NAME = "vectors.npz"

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
        self._ids: np.ndarray = np.empty(0, dtype=str)
        self._documents: np.ndarray = np.empty(0, dtype=str)
        self._metadata_json: np.ndarray = np.empty(0, dtype=str)
        self._embeddings: np.ndarray = np.empty((0, 0), dtype=np.float32)
        self._load()
        try:
            self._validate_embedding_dimension()
        except ValidationAppError as exc:
            if not self._should_auto_repair_dimension_mismatch(exc):
                raise
            self._repair_dimension_mismatch(exc)

    @property
    def _index_path(self) -> Path:
        return Path(self.persist_directory) / self._FILE_NAME

    def _load(self) -> None:
        """加载单文件索引；旧 Chroma 文件不参与读取，等待显式重建。"""

        path = self._index_path
        if not path.exists():
            Path(self.persist_directory).mkdir(parents=True, exist_ok=True)
            return
        try:
            with np.load(path, allow_pickle=False) as data:
                ids = np.asarray(data["ids"], dtype=str)
                documents = np.asarray(data["documents"], dtype=str)
                metadata_json = np.asarray(data["metadata_json"], dtype=str)
                embeddings = np.asarray(data["embeddings"], dtype=np.float32)
        except Exception as exc:  # noqa: BLE001
            raise ValidationAppError(
                "读取本地向量索引失败",
                details={"index_path": str(path), "reason": str(exc)},
            ) from exc
        if embeddings.ndim != 2 or not (len(ids) == len(documents) == len(metadata_json) == len(embeddings)):
            raise ValidationAppError(
                "本地向量索引文件不完整",
                details={"index_path": str(path)},
            )
        self._ids, self._documents, self._metadata_json, self._embeddings = (
            ids,
            documents,
            metadata_json,
            embeddings,
        )

    def _persist(self) -> None:
        """事务式写入：临时文件刷盘后原子替换正式索引。"""

        directory = Path(self.persist_directory)
        directory.mkdir(parents=True, exist_ok=True)
        temp_path = directory / f"{self._FILE_NAME}.tmp"
        try:
            with temp_path.open("wb") as handle:
                np.savez_compressed(
                    handle,
                    ids=self._ids,
                    documents=self._documents,
                    metadata_json=self._metadata_json,
                    embeddings=self._embeddings.astype(np.float32, copy=False),
                )
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self._index_path)
        except Exception as exc:  # noqa: BLE001
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise ValidationAppError(
                "写入本地向量索引失败",
                details={"index_path": str(self._index_path), "reason": str(exc)},
            ) from exc

    def _validate_embedding_dimension(self) -> None:
        """启动时校验当前模型维度与已保存索引维度。"""

        vectors = self.embedding.embed_texts(["embedding-dimension-self-check"])
        if not vectors or not vectors[0]:
            raise ValidationAppError("启动时无法探测当前 Embedding 维度")
        current_dimension = len(vectors[0])
        self.embedding_dimension = current_dimension
        stored_dimension = int(self._embeddings.shape[1]) if self._embeddings.size else None
        if stored_dimension is not None and stored_dimension != current_dimension:
            raise ValidationAppError(
                "当前 Embedding 维度与现有向量索引不一致，请备份后重建本地向量索引",
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
        """清空旧索引并从 SQLite 回填。"""

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
                details={**(exc.details or {}), "repair_error": str(repair_exc)},
            ) from repair_exc

    def reset_collection(self) -> None:
        """清空并持久化空索引。"""

        self._ids = np.empty(0, dtype=str)
        self._documents = np.empty(0, dtype=str)
        self._metadata_json = np.empty(0, dtype=str)
        self._embeddings = np.empty((0, self.embedding_dimension), dtype=np.float32)
        self._persist()

    def close(self) -> None:
        """兼容旧调用方；NumPy 索引无外部句柄需要释放。"""

    def rebuild_from_sqlite(self, *, page_size: int = 100) -> tuple[int, int]:
        """基于 SQLite 已存储的 chunks 重建整个向量集合。"""

        if not self.sqlite_db_path:
            raise ValidationAppError("缺少 sqlite_db_path，无法自动重建向量集合")
        repository = DocumentRepository(Path(self.sqlite_db_path))
        repaired_docs = repaired_chunks = 0
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
                self.upsert_chunks(
                    [{**item, "knowledge_base_id": knowledge_base_id} for item in chunk_items],
                    batch_size=32,
                )
                repaired_docs += 1
                repaired_chunks += len(chunk_items)
            if page * page_size >= total:
                break
            page += 1
        return repaired_docs, repaired_chunks

    def upsert_chunks(self, items: list[dict], *, batch_size: int = 8, progress_callback=None) -> None:
        """批量写入 chunk 向量记录，并在完成后原子保存。"""

        if not items:
            return
        total = len(items)
        new_records: dict[str, tuple[str, str, Any]] = {}
        for start in range(0, total, batch_size):
            batch = items[start : start + batch_size]
            documents = [str(item["content"]) for item in batch]
            raw_vectors = np.asarray(self.embedding.embed_texts(documents), dtype=np.float32)
            if raw_vectors.ndim != 2 or len(raw_vectors) != len(batch):
                raise ValidationAppError("Embedding 返回数量与 chunk 数量不一致")
            if raw_vectors.shape[1] != self.embedding_dimension:
                raise ValidationAppError("Embedding 返回维度与当前索引不一致")
            if not np.isfinite(raw_vectors).all():
                raise ValidationAppError("Embedding 返回了无效数值")
            for item, vector in zip(batch, raw_vectors):
                metadata: dict[str, Any] = {
                    "doc_uid": str(item["doc_uid"]),
                    "chunk_id": str(item["chunk_id"]),
                    "source_span": item.get("source_span") or "",
                    "heading_path": item.get("heading_path") or "",
                    "source_anchor": item.get("source_anchor") or "",
                    "chunk_type": item.get("chunk_type") or "",
                    "content_hash": item.get("content_hash") or "",
                    "knowledge_base_id": item.get("knowledge_base_id") or "",
                    "embedding_model": self.embedding_model,
                    "embedding_dimension": self.embedding_dimension,
                    "index_version": self.index_version,
                }
                for trace_key in ("source_start_line", "source_end_line", "page_no"):
                    if item.get(trace_key) is not None:
                        metadata[trace_key] = int(item[trace_key])
                chunk_id = str(item["chunk_id"])
                new_records[chunk_id] = (str(item["content"]), json.dumps(metadata, ensure_ascii=False, sort_keys=True), vector)
            if progress_callback:
                progress_callback({"completed_chunks": min(start + len(batch), total), "total_chunks": total, "batch_size": len(batch)})

        existing: dict[str, tuple[str, str, Any]] = {
            str(chunk_id): (str(self._documents[index]), str(self._metadata_json[index]), self._embeddings[index])
            for index, chunk_id in enumerate(self._ids)
        }
        existing.update(new_records)
        ordered_ids = sorted(existing)
        self._ids = np.asarray(ordered_ids, dtype=str)
        self._documents = np.asarray([existing[key][0] for key in ordered_ids], dtype=str)
        self._metadata_json = np.asarray([existing[key][1] for key in ordered_ids], dtype=str)
        self._embeddings = np.asarray([existing[key][2] for key in ordered_ids], dtype=np.float32).reshape((-1, self.embedding_dimension))
        self._persist()

    def _metadata(self, index: int) -> dict[str, Any]:
        try:
            value = json.loads(str(self._metadata_json[index]))
        except (json.JSONDecodeError, TypeError) as exc:
            raise ValidationAppError("本地向量索引元数据损坏", details={"index": index}) from exc
        return value if isinstance(value, dict) else {}

    def delete_by_doc_uid(self, doc_uid: str) -> None:
        """按文档标识删除旧向量。"""

        if not doc_uid or not len(self._ids):
            return
        keep = np.asarray([self._metadata(index).get("doc_uid") != doc_uid for index in range(len(self._ids))], dtype=bool)
        if keep.all():
            return
        self._ids, self._documents, self._metadata_json, self._embeddings = self._ids[keep], self._documents[keep], self._metadata_json[keep], self._embeddings[keep]
        self._persist()

    def count_by_doc_uid(self, doc_uid: str) -> int:
        """统计指定文档当前已写入的向量条数。"""

        if not doc_uid:
            return 0
        return sum(self._metadata(index).get("doc_uid") == doc_uid for index in range(len(self._ids)))

    def inspect_index(self) -> dict:
        """汇总向量数量、归属和必填模型元数据。"""

        required_fields = ("chunk_id", "doc_uid", "knowledge_base_id", "embedding_model", "embedding_dimension", "index_version")
        by_knowledge_base: dict[str, int] = {}
        by_document: dict[str, int] = {}
        models: set[str] = set()
        dimensions: set[int] = set()
        versions: set[str] = set()
        missing_metadata_count = 0
        for index in range(len(self._ids)):
            metadata = self._metadata(index)
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
        return {"total_count": len(self._ids), "by_knowledge_base": by_knowledge_base, "by_document": by_document, "missing_metadata_count": missing_metadata_count, "embedding_models": sorted(models), "embedding_dimensions": sorted(dimensions), "index_versions": sorted(versions)}

    def query(self, query_text: str, top_k: int = 5, doc_uid: str | None = None, knowledge_base_id: str | None = None, knowledge_base_ids: list[str] | tuple[str, ...] | None = None) -> list[dict]:
        """执行精确余弦检索，支持单知识库或多知识库范围。"""

        scope = normalize_knowledge_base_scope(knowledge_base_id, knowledge_base_ids)
        if scope == () or not len(self._ids) or top_k <= 0:
            return []
        query_vector = np.asarray(self.embedding.embed_texts([query_text]), dtype=np.float32)
        if query_vector.shape != (1, self.embedding_dimension):
            raise ValidationAppError("查询 Embedding 维度与索引不一致")
        query_norm = float(np.linalg.norm(query_vector[0]))
        if query_norm == 0:
            return []
        candidates: list[tuple[float, str, int]] = []
        for index, chunk_id in enumerate(self._ids):
            metadata = self._metadata(index)
            if doc_uid and metadata.get("doc_uid") != doc_uid:
                continue
            if scope and metadata.get("knowledge_base_id") not in scope:
                continue
            vector_norm = float(np.linalg.norm(self._embeddings[index]))
            score = float(np.dot(query_vector[0], self._embeddings[index]) / (query_norm * vector_norm)) if vector_norm else 0.0
            candidates.append((score, str(chunk_id), index))
        candidates.sort(key=lambda item: (-item[0], item[1]))
        results: list[dict] = []
        for score, _, index in candidates[:top_k]:
            metadata = self._metadata(index)
            results.append({**{key: metadata.get(key) for key in ("chunk_id", "doc_uid", "source_span", "heading_path", "source_start_line", "source_end_line", "page_no", "source_anchor", "chunk_type", "content_hash")}, "content": str(self._documents[index]), "score": score})
        return results
