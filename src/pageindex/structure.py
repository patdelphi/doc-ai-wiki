"""程序说明：构建 Markdown 层级树、增强 PageIndex vendor 节点并执行结构质量门禁。"""

from __future__ import annotations

import re
from hashlib import sha256


def build_heading_tree(markdown_text: str) -> list[dict]:
    """按 ATX 标题级别构建带原文行号和路径的 Markdown 树。"""

    lines = str(markdown_text or "").splitlines()
    heading_levels = _collect_heading_levels(lines)
    recover_flat_hierarchy = len(heading_levels) > 1 and len(set(heading_levels)) == 1
    roots: list[dict] = []
    stack: list[dict] = []
    in_fence = False
    fence_marker = ""
    flat_heading_index = 0
    chapter_active = False
    previous_inferred_level = 1

    for line_number, line in enumerate(lines, start=1):
        stripped = line.lstrip()
        fence_match = re.match(r"^(```+|~~~+)", stripped)
        if fence_match:
            marker = fence_match.group(1)[0]
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif marker == fence_marker:
                in_fence = False
                fence_marker = ""
            continue
        if in_fence:
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", stripped)
        if not heading_match:
            continue
        title = heading_match.group(2).strip()
        if not title:
            continue
        level = len(heading_match.group(1))
        if recover_flat_hierarchy:
            level, chapter_active = _infer_flat_heading_level(
                title,
                index=flat_heading_index,
                chapter_active=chapter_active,
                previous_level=previous_inferred_level,
            )
            flat_heading_index += 1
            previous_inferred_level = level

        while stack and int(stack[-1]["level"]) >= level:
            stack.pop()["source_end_line"] = line_number - 1
        parent = stack[-1] if stack else None
        heading_path = " / ".join(
            [str(item["title"]) for item in stack] + [title]
        )
        node: dict = {
            "title": title,
            "level": level,
            "line_num": line_number,
            "heading_path": heading_path,
            "source_start_line": line_number,
            "source_end_line": len(lines),
            "source_anchor": _build_anchor(title, line_number),
            "content_hash": "",
            "children": [],
        }
        if parent is None:
            roots.append(node)
        else:
            parent["children"].append(node)
        stack.append(node)

    for node in stack:
        node["source_end_line"] = len(lines)

    def fill_content_hash(nodes: list[dict]) -> None:
        for node in nodes:
            start = max(int(node["source_start_line"]) - 1, 0)
            end = max(int(node["source_end_line"]), start)
            content = "\n".join(lines[start:end])
            node["content_hash"] = sha256(content.encode("utf-8")).hexdigest()
            node["text"] = content
            summary_text = " ".join(
                line.strip()
                for line in content.splitlines()[1:]
                if line.strip()
            )
            node["summary"] = summary_text[:500]
            fill_content_hash(node["children"])

    fill_content_hash(roots)
    return roots


def _collect_heading_levels(lines: list[str]) -> list[int]:
    """统计代码围栏外的 ATX 标题级别，用于识别转换器造成的全 H1 文档。"""

    levels: list[int] = []
    in_fence = False
    fence_marker = ""
    for line in lines:
        stripped = line.lstrip()
        fence_match = re.match(r"^(```+|~~~+)", stripped)
        if fence_match:
            marker = fence_match.group(1)[0]
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif marker == fence_marker:
                in_fence = False
                fence_marker = ""
            continue
        if in_fence:
            continue
        heading_match = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", stripped)
        if heading_match and heading_match.group(2).strip():
            levels.append(len(heading_match.group(1)))
    return levels


def _infer_flat_heading_level(
    title: str,
    *,
    index: int,
    chapter_active: bool,
    previous_level: int,
) -> tuple[int, bool]:
    """按文档根、卷章标记和数字编号恢复被压平的 Markdown 标题层级。"""

    normalized = re.sub(r"\s+", " ", str(title or "")).strip()
    if index == 0:
        return 1, False
    if re.match(r"^(?:卷+\s*[一二三四五六七八九十百零〇\d]+|第\s*[一二三四五六七八九十百零〇\d]+\s*[章节篇])", normalized):
        return 2, True

    numeric_match = re.match(r"^(\d+(?:\s*\.\s*\d+)*)\s*", normalized)
    if numeric_match:
        depth = numeric_match.group(1).count(".")
        base_level = 4 if chapter_active else 3
        return min(base_level + depth, 6), chapter_active
    if re.match(r"^[一二三四五六七八九十百]+[、．.]", normalized):
        return (4 if chapter_active else 2), chapter_active
    if re.match(r"^(?:参考文献|参考资料|结论|结语|结束语|小结|引言|前言)\s*[:：]?$", normalized):
        return (4 if chapter_active else 3), chapter_active

    latin_count = len(re.findall(r"[A-Za-z]", normalized))
    visible_count = len(re.sub(r"\s+", "", normalized))
    if not chapter_active and previous_level == 2 and visible_count and latin_count / visible_count >= 0.6:
        return 3, chapter_active
    return (3 if chapter_active else 2), chapter_active


def enrich_vendor_structure(
    vendor_nodes: list[dict],
    heading_tree: list[dict],
    doc_uid: str,
) -> list[dict]:
    """用 Markdown 标题路径和范围增强 vendor 结构，并生成稳定节点 ID。"""

    flattened_vendor = _flatten_vendor_nodes(vendor_nodes)
    used_vendor_indexes: set[int] = set()

    def convert_heading_nodes(
        heading_nodes: list[dict],
        parent_id: str | None,
    ) -> list[dict]:
        converted: list[dict] = []
        for heading in heading_nodes:
            vendor_index, vendor = _match_vendor_node(
                flattened_vendor,
                heading,
                used_vendor_indexes,
            )
            if vendor_index is not None:
                used_vendor_indexes.add(vendor_index)
            start_line = int(heading.get("source_start_line") or 0)
            end_line = int(heading.get("source_end_line") or start_line)
            heading_path = str(heading.get("heading_path") or heading.get("title") or "")
            node_id = _stable_node_id(doc_uid, heading_path, start_line, end_line)
            node = {
                **(vendor or {}),
                "title": str(heading.get("title") or (vendor or {}).get("title") or ""),
                "node_id": node_id,
                "parent_id": parent_id,
                "level": int(heading.get("level") or 1),
                "line_num": int((vendor or {}).get("line_num") or start_line),
                "heading_path": heading_path,
                "source_start_line": start_line,
                "source_end_line": end_line,
                "source_anchor": str(heading.get("source_anchor") or ""),
                "content_hash": str(heading.get("content_hash") or ""),
                "text": str(heading.get("text") or (vendor or {}).get("text") or ""),
                "summary": str(
                    (vendor or {}).get("summary")
                    or heading.get("summary")
                    or ""
                ),
            }
            node.pop("children", None)
            node["nodes"] = convert_heading_nodes(
                list(heading.get("children") or []),
                node_id,
            )
            converted.append(node)
        return converted

    if heading_tree:
        return convert_heading_nodes(heading_tree, None)
    return _enrich_vendor_without_headings(vendor_nodes, str(doc_uid or ""))


def evaluate_tree_quality(structure: list[dict], source_line_count: int) -> dict:
    """检查树深度、追溯字段、孤立节点、空节点和正文覆盖率。"""

    flattened: list[tuple[dict, int]] = []

    def walk(nodes: list[dict], depth: int) -> None:
        for node in nodes:
            if not isinstance(node, dict):
                continue
            flattened.append((node, depth))
            nodes_value = node.get("nodes")
            children_value = node.get("children")
            raw_children: list = []
            if isinstance(nodes_value, list):
                raw_children = nodes_value
            elif isinstance(children_value, list):
                raw_children = children_value
            children: list[dict] = [item for item in raw_children if isinstance(item, dict)]
            walk(children, depth + 1)

    walk(structure if isinstance(structure, list) else [], 1)
    errors: list[str] = []
    node_count = len(flattened)
    max_depth = max((depth for _, depth in flattened), default=0)
    if not flattened:
        errors.append("empty_tree")
    if node_count > 1 and max_depth <= 1:
        errors.append("flat_tree")

    node_ids = [str(node.get("node_id") or "") for node, _ in flattened]
    valid_ids = {node_id for node_id in node_ids if node_id}
    empty_node_count = sum(1 for node, _ in flattened if not str(node.get("title") or "").strip())
    orphan_node_count = sum(
        1
        for node, _ in flattened
        if node.get("parent_id") and str(node.get("parent_id")) not in valid_ids
    )
    duplicate_node_id_count = len([item for item in node_ids if item]) - len(valid_ids)
    traceable_count = sum(
        1
        for node, _ in flattened
        if (
            node.get("source_start_line") is not None
            and node.get("source_end_line") is not None
            and str(node.get("source_anchor") or "").strip()
        )
        or node.get("page")
        or node.get("start_index")
    )
    traceability_rate = traceable_count / node_count if node_count else 0.0
    coverage_rate = _calculate_line_coverage(flattened, max(int(source_line_count or 0), 0))

    if empty_node_count:
        errors.append("empty_nodes")
    if orphan_node_count:
        errors.append("orphan_nodes")
    if duplicate_node_id_count or any(not node_id for node_id in node_ids):
        errors.append("invalid_node_ids")
    if node_count and traceability_rate < 1.0:
        errors.append("traceability_incomplete")
    if source_line_count > 0 and coverage_rate < 0.7:
        errors.append("source_coverage_low")

    return {
        "passed": not errors,
        "errors": errors,
        "node_count": node_count,
        "root_node_count": len(structure) if isinstance(structure, list) else 0,
        "max_depth": max_depth,
        "empty_node_count": empty_node_count,
        "orphan_node_count": orphan_node_count,
        "duplicate_node_id_count": duplicate_node_id_count,
        "traceability_rate": round(traceability_rate, 4),
        "source_coverage_rate": round(coverage_rate, 4),
    }


def _flatten_vendor_nodes(nodes: list[dict]) -> list[dict]:
    """展开 vendor 树以便按标题与行号匹配。"""

    flattened: list[dict] = []
    for node in nodes if isinstance(nodes, list) else []:
        if not isinstance(node, dict):
            continue
        flattened.append(node)
        flattened.extend(_flatten_vendor_nodes(node.get("nodes") or []))
    return flattened


def _match_vendor_node(
    vendor_nodes: list[dict],
    heading: dict,
    used_indexes: set[int],
) -> tuple[int | None, dict | None]:
    """优先按规范化标题匹配，再以行号距离消除重名歧义。"""

    heading_title = _normalize_title(heading.get("title"))
    heading_line = int(heading.get("source_start_line") or 0)
    candidates = [
        (index, node)
        for index, node in enumerate(vendor_nodes)
        if index not in used_indexes and _normalize_title(node.get("title")) == heading_title
    ]
    if not candidates:
        candidates = [
            (index, node)
            for index, node in enumerate(vendor_nodes)
            if index not in used_indexes and int(node.get("line_num") or 0) == heading_line
        ]
    if not candidates:
        return None, None
    return min(candidates, key=lambda item: abs(int(item[1].get("line_num") or 0) - heading_line))


def _enrich_vendor_without_headings(vendor_nodes: list[dict], doc_uid: str) -> list[dict]:
    """为 PDF 或旧结构补齐稳定 ID，同时保留 vendor 原层级。"""

    def walk(nodes: list[dict], titles: list[str], parent_id: str | None) -> list[dict]:
        converted: list[dict] = []
        for index, vendor in enumerate(nodes if isinstance(nodes, list) else []):
            if not isinstance(vendor, dict):
                continue
            title = str(vendor.get("title") or "")
            heading_path = " / ".join([*titles, title])
            start = int(vendor.get("line_num") or vendor.get("start_index") or vendor.get("page") or index + 1)
            end = int(vendor.get("end_line") or vendor.get("end_index") or start)
            node_id = _stable_node_id(doc_uid, heading_path, start, end)
            node = {
                **vendor,
                "node_id": node_id,
                "parent_id": parent_id,
                "level": len(titles) + 1,
                "heading_path": heading_path,
                "source_start_line": start if vendor.get("line_num") else None,
                "source_end_line": end if vendor.get("line_num") else None,
                "source_anchor": _build_anchor(title, start),
                "content_hash": sha256(
                    str(vendor.get("text") or vendor.get("summary") or heading_path).encode("utf-8")
                ).hexdigest(),
            }
            node["nodes"] = walk(vendor.get("nodes") or [], [*titles, title], node_id)
            converted.append(node)
        return converted

    return walk(vendor_nodes, [], None)


def _calculate_line_coverage(flattened: list[tuple[dict, int]], source_line_count: int) -> float:
    """按节点原文范围的并集计算正文覆盖率。"""

    if source_line_count <= 0:
        return 1.0 if flattened else 0.0
    covered_lines: set[int] = set()
    for node, _ in flattened:
        start = int(node.get("source_start_line") or 0)
        end = int(node.get("source_end_line") or 0)
        if start <= 0 or end < start:
            continue
        covered_lines.update(range(max(start, 1), min(end, source_line_count) + 1))
    return min(len(covered_lines) / source_line_count, 1.0)


def _stable_node_id(doc_uid: str, heading_path: str, start_line: int, end_line: int) -> str:
    """根据文档、路径和原文范围生成可重复的节点 ID。"""

    payload = f"{doc_uid}|{heading_path}|{start_line}|{end_line}"
    return sha256(payload.encode("utf-8")).hexdigest()[:20]


def _build_anchor(title: str, line_number: int) -> str:
    """生成便于人工核对的稳定标题锚点。"""

    normalized = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "-", str(title or "")).strip("-").lower()
    return f"{normalized or 'heading'}-L{int(line_number)}"


def _normalize_title(value: object) -> str:
    """规范化标题以支持 vendor 与 Markdown 的保守匹配。"""

    return re.sub(r"\s+", "", str(value or "")).strip("#：:。.").casefold()
