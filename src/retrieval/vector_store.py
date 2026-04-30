"""程序说明：封装 ChromaDB 持久化向量索引与查询逻辑。"""

from __future__ import annotations

from hashlib import md5

import chromadb


class DeterministicEmbedding:
    """基于字符哈希的确定性嵌入，便于本地开发与测试。"""

    def __init__(self, dimension: int = 64) -> None:
        self.dimension = dimension

    def embed_text(self, text: str) -> list[float]:
        """将文本映射为固定维度向量。"""

        vector = [0.0] * self.dimension
        normalized = text.strip()
        if not normalized:
            return vector

        for char in normalized:
            digest = md5(char.encode("utf-8"), usedforsecurity=False).digest()
            index = digest[0] % self.dimension
            vector[index] += ((digest[1] % 17) + 1) / 17.0

        scale = float(len(normalized))
        return [value / scale for value in vector]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """批量嵌入文本。"""

        return [self.embed_text(text) for text in texts]


class VectorStore:
    """ChromaDB 向量集合封装。"""

    def __init__(self, persist_directory, collection_name: str = "knowledge_chunks") -> None:
        self.client = chromadb.PersistentClient(path=str(persist_directory))
        self.collection = self.client.get_or_create_collection(name=collection_name)
        self.embedding = DeterministicEmbedding()

    def upsert_chunks(self, items: list[dict]) -> None:
        """批量写入 chunk 向量记录。"""

        if not items:
            return

        documents = [item["content"] for item in items]
        metadatas = [
            {
                "doc_uid": item["doc_uid"],
                "chunk_id": item["chunk_id"],
                "source_span": item.get("source_span") or "",
            }
            for item in items
        ]
        self.collection.upsert(
            ids=[item["chunk_id"] for item in items],
            documents=documents,
            metadatas=metadatas,
            embeddings=self.embedding.embed_texts(documents),
        )

    def delete_by_doc_uid(self, doc_uid: str) -> None:
        """按文档标识删除旧向量。"""

        self.collection.delete(where={"doc_uid": doc_uid})

    def query(self, query_text: str, top_k: int = 5) -> list[dict]:
        """执行向量检索。"""

        result = self.collection.query(
            query_embeddings=[self.embedding.embed_text(query_text)],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
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
