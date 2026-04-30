"""程序说明：验证 Markdown 章节解析逻辑。"""

from src.metadata.sections import parse_markdown_sections


def test_parse_markdown_sections_should_preserve_heading_structure() -> None:
    """带标题的 Markdown 应解析出对应章节结构。"""

    content = """# 总标题

导语内容。

## 第一节

第一节内容。

## 第二节

第二节内容。
"""

    sections = parse_markdown_sections(content, fallback_title="默认标题")

    assert len(sections) == 3
    assert sections[0]["section_title"] == "总标题"
    assert sections[0]["section_level"] == 1
    assert sections[1]["section_title"] == "第一节"
    assert sections[1]["section_level"] == 2
    assert "第一节内容" in sections[1]["content"]
    assert sections[2]["section_title"] == "第二节"
