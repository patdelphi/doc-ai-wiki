"""程序说明：验证 PageIndex 确定性树候选算法及交叉引用处理。"""

from __future__ import annotations

from src.pageindex.tree_retriever import (
    build_tree_candidates,
    candidate_to_debug,
    extract_cross_reference_targets,
    find_cross_reference_candidates,
    flatten_structure,
    format_node_position,
    merge_tree_candidates,
    penalize_generic_front_matter,
    score_node,
)


def test_flatten_structure_should_use_depth_first_order_and_skip_invalid_nodes() -> None:
    """树展开应保持深度优先顺序，并跳过非字典节点。"""

    structure = [
        {
            "title": "第一章",
            "nodes": [
                {"title": "第一节", "nodes": []},
                "invalid",
            ],
        },
        {"title": "第二章", "nodes": []},
    ]

    assert [node["title"] for node in flatten_structure(structure)] == ["第一章", "第一节", "第二章"]


def test_score_node_should_prefer_title_match_and_support_compact_text() -> None:
    """标题命中应加四分，摘要或正文命中应加两分。"""

    node = {
        "title": "阿胶质量检测",
        "summary": "含量 测定方法",
        "text": "用于生产过程控制。",
    }

    assert score_node(node, ["质量检测", "含量测定", "生产过程"]) == 8


def test_penalize_generic_front_matter_should_keep_existing_rules() -> None:
    """泛化前置节点和页码式文本应按原规则降分且不低于零。"""

    node = {"title": "图书在版 CIP/12", "summary": "全集/3", "line_num": 10}

    assert penalize_generic_front_matter(node, 30) == 12
    assert penalize_generic_front_matter(node, 5) == 0


def test_build_tree_candidates_should_preserve_sort_ids_limits_and_truncation() -> None:
    """候选构建应保持原排序、展开序号 ID、数量和字段截断。"""

    structure = [
        {
            "title": "质量说明",
            "level": 2,
            "line_num": 20,
            "summary": "质量" + "摘" * 600,
            "nodes": [],
        },
        {
            "title": "质量标准",
            "level": 1,
            "line_num": 30,
            "summary": "质量检测标准",
            "nodes": [],
        },
        {
            "title": "生产工艺",
            "level": 1,
            "line_num": 5,
            "summary": "无关",
            "nodes": [],
        },
    ]
    loaded_lines: list[int] = []

    def load_content(node: dict) -> str:
        """记录被读取节点，并返回超过候选上限的原文。"""

        loaded_lines.append(int(node["line_num"]))
        return "原" * 1000

    candidates = build_tree_candidates(structure, ["质量", "标准"], limit=1, content_loader=load_content)

    assert len(candidates) == 1
    assert candidates[0]["candidate_id"] == "node_2"
    assert candidates[0]["position"] == "line 30"
    assert len(candidates[0]["summary"]) <= 500
    assert len(candidates[0]["content_excerpt"]) == 900
    assert loaded_lines == [30]


def test_build_tree_candidates_should_not_load_content_without_loader() -> None:
    """未注入原文 loader 时，候选内容摘录应保持为空。"""

    candidates = build_tree_candidates(
        [{"title": "质量标准", "level": 1, "line_num": 8, "nodes": []}],
        ["质量"],
        limit=5,
    )

    assert candidates[0]["content_excerpt"] == ""


def test_cross_reference_flow_should_extract_match_and_deduplicate() -> None:
    """交叉引用目标应按原顺序提取，并匹配唯一树候选。"""

    targets = extract_cross_reference_targets(
        "主文提到详见附录 G；另参见表 5.3，见第六章，并详见“质量标准”。"
    )
    structure = [
        {"title": "附录 G", "summary": "统计表格", "line_num": 50, "level": 1, "nodes": []},
        {"title": "质量标准", "summary": "检测依据", "line_num": 80, "level": 1, "nodes": []},
        {"title": "质量标准", "summary": "重复", "line_num": 80, "level": 1, "nodes": []},
    ]
    candidates = find_cross_reference_candidates(structure, targets)

    assert targets == ["附录 G", "表 5.3", "第六章", "质量标准"]
    assert [item["title"] for item in candidates] == ["附录 G", "质量标准"]
    assert [item["candidate_id"] for item in candidates] == ["xref_1", "xref_2"]
    assert candidates[0]["reason"] == "交叉引用候选"


def test_merge_tree_candidates_should_use_title_position_or_candidate_id() -> None:
    """候选合并应按标题位置去重，空标题位置时回退到候选 ID。"""

    primary = [
        {"candidate_id": "xref_1", "title": "附录 G", "position": "line 50"},
        {"candidate_id": "empty_1", "title": "", "position": ""},
    ]
    supplemental = [
        {"candidate_id": "node_2", "title": "附录 G", "position": "line 50"},
        {"candidate_id": "empty_1", "title": "", "position": ""},
        {"candidate_id": "empty_2", "title": "", "position": ""},
    ]

    merged = merge_tree_candidates(primary, supplemental)

    assert [item["candidate_id"] for item in merged] == ["xref_1", "empty_1", "empty_2"]


def test_candidate_debug_and_position_should_preserve_default_fields() -> None:
    """调试字段和页码、行号、空定位格式应保持兼容。"""

    debug = candidate_to_debug(
        {
            "candidate_id": "node_1",
            "title": "质量标准",
            "position": "page 3",
            "summary": "检测依据",
            "score": 4,
            "content_excerpt": "正文",
        }
    )

    assert debug == {
        "candidate_id": "node_1",
        "title": "质量标准",
        "position": "page 3",
        "summary": "检测依据",
        "score": 4,
        "reason": "本地候选召回",
        "content_excerpt": "正文",
    }
    assert format_node_position({"page": 3, "line_num": 9}) == "page 3"
    assert format_node_position({"line_num": 9}) == "line 9"
    assert format_node_position({}) == ""
