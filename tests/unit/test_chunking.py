"""程序说明：验证最小文本分块逻辑。"""

from src.chunking.splitter import split_text


def test_split_text_should_return_multiple_chunks_when_content_is_long() -> None:
    """长文本应被拆分为多个 chunk。"""

    content = "甲" * 1200
    chunks = split_text(content, chunk_size=500, chunk_overlap=100)

    assert len(chunks) >= 3
    assert all(chunks)
