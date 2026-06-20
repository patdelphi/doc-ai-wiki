"""程序说明：验证最小文本分块逻辑。"""

from src.chunking.splitter import split_text


def test_split_text_should_return_multiple_chunks_when_content_is_long() -> None:
    """长文本应被拆分为多个 chunk。"""

    content = "甲" * 1200
    chunks = split_text(content, chunk_size=500, chunk_overlap=100)

    assert len(chunks) >= 3
    assert all(chunks)


def test_split_text_should_keep_markdown_table_together() -> None:
    """Markdown 表格应作为完整语义块进入同一个 chunk。"""

    content = """段落一。

| 项目 | 说明 |
|---|---|
| 阿胶 | 补血滋阴 |
| 黄酒 | 炮制辅料 |

段落二。
"""

    chunks = split_text(content, chunk_size=35, chunk_overlap=0)

    table_chunks = [chunk for chunk in chunks if "| 项目 | 说明 |" in chunk]
    assert len(table_chunks) == 1
    assert "| 阿胶 | 补血滋阴 |" in table_chunks[0]
    assert "| 黄酒 | 炮制辅料 |" in table_chunks[0]


def test_split_text_should_keep_fenced_code_block_together() -> None:
    """围栏代码块应作为完整语义块进入同一个 chunk。"""

    content = """说明文字。

```python
def main():
    return "阿胶"
```

后续文字。
"""

    chunks = split_text(content, chunk_size=30, chunk_overlap=0)

    code_chunks = [chunk for chunk in chunks if "```python" in chunk]
    assert len(code_chunks) == 1
    assert 'return "阿胶"' in code_chunks[0]
    assert code_chunks[0].strip().endswith("```")


def test_split_text_should_keep_blockquote_together() -> None:
    """连续引用块应作为完整语义块进入同一个 chunk。"""

    content = """前文。

> 第一条引用说明
> 第二条引用说明

后文。
"""

    chunks = split_text(content, chunk_size=20, chunk_overlap=0)

    quote_chunks = [chunk for chunk in chunks if "> 第一条引用说明" in chunk]
    assert len(quote_chunks) == 1
    assert "> 第二条引用说明" in quote_chunks[0]
