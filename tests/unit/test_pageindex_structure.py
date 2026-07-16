"""程序说明：验证 Markdown 标题树、稳定节点增强和 PageIndex 结构质量门禁。"""

from __future__ import annotations

from src.pageindex.structure import (
    build_heading_tree,
    enrich_vendor_structure,
    evaluate_tree_quality,
)


def test_heading_tree_should_preserve_article_chapter_section_hierarchy() -> None:
    """文章、章、节标题必须保持原始层级和行号。"""

    tree = build_heading_tree("# 第一篇\n## 第一章\n### 第一节\n正文")

    section = tree[0]["children"][0]["children"][0]
    assert section["heading_path"] == "第一篇 / 第一章 / 第一节"
    assert section["source_start_line"] == 3
    assert section["source_end_line"] == 4


def test_enriched_structure_should_use_stable_ids_and_keep_vendor_line_number() -> None:
    """规范化结构应保留 vendor 定位字段并生成稳定父子 ID。"""

    heading_tree = build_heading_tree("# 第一篇\n## 第一章\n正文")
    vendor_nodes = [
        {
            "title": "第一篇",
            "line_num": 1,
            "summary": "总览",
            "nodes": [{"title": "第一章", "line_num": 2, "summary": "章节", "nodes": []}],
        }
    ]

    first = enrich_vendor_structure(vendor_nodes, heading_tree, "doc_1")
    second = enrich_vendor_structure(vendor_nodes, heading_tree, "doc_1")

    assert first == second
    assert first[0]["line_num"] == 1
    assert first[0]["nodes"][0]["parent_id"] == first[0]["node_id"]
    assert first[0]["nodes"][0]["heading_path"] == "第一篇 / 第一章"


def test_tree_quality_should_reject_all_root_nodes() -> None:
    """存在多个节点但没有任何父子层级时应拒绝发布。"""

    structure = [
        {
            "node_id": "one",
            "parent_id": None,
            "title": "一",
            "source_start_line": 1,
            "source_end_line": 50,
            "nodes": [],
        },
        {
            "node_id": "two",
            "parent_id": None,
            "title": "二",
            "source_start_line": 51,
            "source_end_line": 100,
            "nodes": [],
        },
    ]

    report = evaluate_tree_quality(structure, source_line_count=100)

    assert report["passed"] is False
    assert "flat_tree" in report["errors"]


def test_flat_converted_markdown_should_recover_document_root_hierarchy() -> None:
    """转换器把所有标题写成 H1 时，应以首标题为文档根节点恢复层级。"""

    markdown = "\n".join(
        [
            "# 阿胶历史文化通典",
            "# 序",
            "# 卷一 史志典",
            "# 名物",
            "# 一、阿胶",
            "# 二、东阿阿胶",
            "# 卷二 医药典",
            "# 本草记载",
        ]
    )

    tree = build_heading_tree(markdown)

    assert len(tree) == 1
    assert tree[0]["title"] == "阿胶历史文化通典"
    first_chapter = next(node for node in tree[0]["children"] if node["title"] == "卷一 史志典")
    assert first_chapter["children"][0]["title"] == "名物"


def test_flat_article_markdown_should_recover_numeric_subsection_depth() -> None:
    """论文合集的数字标题应按 1、1.1、1.1.1 恢复稳定深度。"""

    markdown = "\n".join(
        [
            "# 阿胶学术论文全集",
            "# 阿胶质量研究进展",
            "# 1 研究背景",
            "# 1.1 原料",
            "# 1.1.1 驴皮",
            "# 2 研究方法",
            "# 参考文献",
        ]
    )

    tree = build_heading_tree(markdown)

    article = tree[0]["children"][0]
    assert article["title"] == "阿胶质量研究进展"
    assert article["children"][0]["title"] == "1 研究背景"
    assert article["children"][0]["children"][0]["title"] == "1.1 原料"
