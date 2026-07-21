"""程序说明：提供 PageIndex 树候选召回、交叉引用和调试格式化的确定性算法。"""

from __future__ import annotations

import re
from collections.abc import Callable


ContentLoader = Callable[[dict], str]


def flatten_structure(structure: list[dict]) -> list[dict]:
    """将 PageIndex 树结构展开为深度优先列表。"""
    items: list[dict] = []

    def walk(nodes: list[dict]) -> None:
        for node in nodes:
            if not isinstance(node, dict):
                continue
            items.append(node)
            children = node.get("nodes")
            if isinstance(children, list):
                walk(children)
    walk(structure)
    return items


def format_node_position(node: dict) -> str:
    """格式化节点定位信息，页码优先于行号。"""
    position_key = "page" if node.get("page") else "line_num" if node.get("line_num") else ""
    return f"{position_key.removesuffix('_num')} {node.get(position_key)}" if position_key else ""


def score_node(node: dict, terms: list[str]) -> int:
    """按标题、摘要和节点原文对候选节点打分。"""
    fields = ("title", "summary", "prefix_summary", "text")
    haystack = " ".join(str(node.get(field) or "") for field in fields).lower()
    compact_haystack = re.sub(r"\s+", "", haystack)
    title_text = str(node.get("title") or "").lower()
    compact_title = re.sub(r"\s+", "", title_text)
    score = 0
    for term in terms:
        normalized = term.lower()
        if not normalized:
            continue
        compact_normalized = re.sub(r"\s+", "", normalized)
        if normalized in title_text or compact_normalized in compact_title:
            score += 4
        elif normalized in haystack or compact_normalized in compact_haystack:
            score += 2
    return score


def penalize_generic_front_matter(node: dict, score: int) -> int:
    """降低文档标题、课题组、CIP、参考文献等泛化前置节点排序。"""
    title = str(node.get("title") or "").strip()
    summary = str(node.get("summary") or node.get("prefix_summary") or "").strip()
    line_num = int(node.get("line_num") or 0)
    penalty = 0
    generic_patterns = ("通典", "全集", "课题组", "图书在版", "CIP", "参考文献")
    is_generic = any(pattern in title for pattern in generic_patterns)
    if is_generic:
        penalty += 8
    if is_generic and line_num and line_num <= 80:
        penalty += 4
    if re.search(r"/\d+", title) or re.search(r"/\d+", summary):
        penalty += 6
    return max(score - penalty, 0)


def build_tree_candidates(
    structure: list[dict],
    terms: list[str],
    *,
    limit: int,
    content_loader: ContentLoader | None = None,
) -> list[dict]:
    """按原有分数与稳定展开序号构建树候选。"""
    scored_items: list[tuple[int, int, dict]] = []
    for index, node in enumerate(flatten_structure(structure), start=1):
        score = penalize_generic_front_matter(node, score_node(node, terms))
        scored_items.append((score, index, node))
    scored_items.sort(
        key=lambda item: (-item[0], int(item[2].get("level") or 1), int(item[2].get("line_num") or 0))
    )
    candidates: list[dict] = []
    for score, original_index, node in (item for item in scored_items if item[0] > 0):
        if len(candidates) >= limit:
            break
        content_excerpt = content_loader(node)[:900] if content_loader is not None else ""
        candidates.append(
            {
                "candidate_id": f"node_{original_index}",
                "title": str(node.get("title") or ""),
                "level": int(node.get("level") or 1),
                "position": format_node_position(node),
                "summary": str(node.get("summary") or node.get("prefix_summary") or "")[:500],
                "content_excerpt": content_excerpt,
                "score": score,
                "node": node,
            }
        )
    return candidates


def extract_cross_reference_targets(content: str) -> list[str]:
    """从节点原文中提取明确的交叉引用目标。"""
    text = str(content or "")
    targets: list[str] = []
    patterns = [
        r"(附录\s*[A-Za-z0-9一二三四五六七八九十]+)",
        r"(表\s*\d+(?:\.\d+)*)",
        r"(图\s*\d+(?:\.\d+)*)",
        r"(第[一二三四五六七八九十百千万\d]+章)",
        r"(?:详见|参见|见)[“\"《]?([^，。；;、“”\"》]{2,30})[”\"》]?",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            target = str(match.group(1) or "").strip()
            target = re.sub(r"^(附录|表|图)([A-Za-z0-9一二三四五六七八九十])", r"\1 \2", target)
            target = re.sub(r"\s+", " ", target).strip(" ：:，。；;、")
            if target and target not in targets:
                targets.append(target)
    return targets


def _normalize_text(value: str) -> str:
    """移除影响交叉引用包含匹配的空白和常见标点。"""
    return re.sub(r"[\s，。！？、,.?？：:；;（）()《》“”\"'`]+", "", str(value or ""))


def find_cross_reference_candidates(structure: list[dict], targets: list[str]) -> list[dict]:
    """按交叉引用目标在树标题和摘要中查找候选节点。"""
    normalized_targets = [_normalize_text(target) for target in targets if str(target or "").strip()]
    candidates: list[dict] = []
    seen_positions: set[str] = set()
    for node in flatten_structure(structure):
        title = str(node.get("title") or "")
        summary = str(node.get("summary") or node.get("prefix_summary") or "")
        haystack = _normalize_text(f"{title} {summary}")
        if not haystack or not any(target and target in haystack for target in normalized_targets):
            continue
        position = format_node_position(node)
        key = f"{title}|{position}"
        if key in seen_positions:
            continue
        seen_positions.add(key)
        candidates.append(
            {
                "candidate_id": f"xref_{len(candidates) + 1}",
                "title": title,
                "level": int(node.get("level") or 1),
                "position": position,
                "summary": summary[:500],
                "content_excerpt": str(node.get("text") or "")[:900],
                "score": 0,
                "reason": "交叉引用候选",
                "node": node,
            }
        )
    return candidates


def merge_tree_candidates(primary: list[dict], supplemental: list[dict]) -> list[dict]:
    """合并树候选，按标题位置和必要时的候选 ID 去重。"""
    merged: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for item in [*(primary or []), *(supplemental or [])]:
        title = str(item.get("title") or "")
        position = str(item.get("position") or "")
        key = (title, position, "" if title or position else str(item.get("candidate_id") or ""))
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def candidate_to_debug(candidate: dict) -> dict:
    """将候选节点转换为前端诊断行所需字段。"""
    return {
        "candidate_id": str(candidate.get("candidate_id") or ""),
        "title": str(candidate.get("title") or ""),
        "position": str(candidate.get("position") or ""),
        "summary": str(candidate.get("summary") or ""),
        "score": int(candidate.get("score") or 0),
        "reason": str(candidate.get("reason") or "本地候选召回"),
        "content_excerpt": str(candidate.get("content_excerpt") or ""),
    }
