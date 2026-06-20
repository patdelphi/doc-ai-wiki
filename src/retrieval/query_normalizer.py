"""程序说明：提供实体词表驱动的查询归一化与别名扩展能力。"""

from __future__ import annotations

from dataclasses import dataclass
import json
from functools import lru_cache
from pathlib import Path
import re


@dataclass(frozen=True)
class EntityDictionary:
    """实体词表，保存异体字映射、标准名与别名关系。"""

    variants: dict[str, str]
    alias_to_canonical: dict[str, str]
    canonical_to_aliases: dict[str, tuple[str, ...]]


def _default_dictionary_path() -> Path:
    """返回项目内置实体词表路径。"""

    return Path(__file__).resolve().parents[2] / "data" / "entities" / "term_dictionary.json"


@lru_cache(maxsize=4)
def load_entity_dictionary(dictionary_path: str | Path | None = None) -> EntityDictionary:
    """加载实体词表；词表缺失或损坏时返回空词表，避免检索链路中断。"""

    path = Path(dictionary_path) if dictionary_path else _default_dictionary_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return EntityDictionary(variants={}, alias_to_canonical={}, canonical_to_aliases={})

    variants = {
        str(source): str(target)
        for source, target in dict(payload.get("variants") or {}).items()
        if str(source) and str(target)
    }
    alias_to_canonical: dict[str, str] = {}
    canonical_to_aliases: dict[str, tuple[str, ...]] = {}
    for entity in payload.get("entities") or []:
        if not isinstance(entity, dict):
            continue
        canonical = str(entity.get("canonical") or "").strip()
        if not canonical:
            continue
        aliases = tuple(
            str(alias).strip()
            for alias in entity.get("aliases") or []
            if str(alias).strip()
        )
        alias_to_canonical[canonical] = canonical
        for alias in aliases:
            alias_to_canonical[alias] = canonical
        canonical_to_aliases[canonical] = tuple(dict.fromkeys((canonical, *aliases)))
    return EntityDictionary(
        variants=variants,
        alias_to_canonical=alias_to_canonical,
        canonical_to_aliases=canonical_to_aliases,
    )


def normalize_query_text(query: str, dictionary: EntityDictionary | None = None) -> str:
    """将查询中的异体字、繁简写法和实体别名替换为标准名。"""

    text = str(query or "")
    entity_dictionary = dictionary or load_entity_dictionary()
    text = _replace_terms(text, entity_dictionary.variants)
    text = _replace_terms(text, entity_dictionary.alias_to_canonical)
    return _compact_spaces(text)


def expand_query_texts(
    query: str,
    dictionary: EntityDictionary | None = None,
    *,
    limit: int = 8,
) -> list[str]:
    """基于实体词表扩展查询，优先返回原始查询、标准名查询和常见别名查询。"""

    entity_dictionary = dictionary or load_entity_dictionary()
    original = _compact_spaces(str(query or ""))
    if not original:
        return []

    candidates = [original]
    normalized = normalize_query_text(original, entity_dictionary)
    candidates.append(normalized)

    for canonical, aliases in entity_dictionary.canonical_to_aliases.items():
        if canonical not in normalized:
            continue
        for alias in aliases:
            if alias == canonical:
                continue
            candidates.append(normalized.replace(canonical, alias))

    return _deduplicate_non_empty(candidates)[: max(int(limit), 1)]


def build_normalized_index_text(text: str, dictionary: EntityDictionary | None = None) -> str:
    """构建入库索引文本，保留原文并追加归一文本，避免改写原始内容。"""

    original = str(text or "")
    normalized = normalize_query_text(original, dictionary)
    return "\n".join(_deduplicate_non_empty([original, normalized]))


def _replace_terms(text: str, replacements: dict[str, str]) -> str:
    """按长词优先替换，避免短词先替换破坏长实体。"""

    result = text
    for source in sorted(replacements, key=len, reverse=True):
        target = replacements[source]
        if source and target:
            result = result.replace(source, target)
    return result


def _compact_spaces(text: str) -> str:
    """压缩查询中的连续空白。"""

    return re.sub(r"\s+", " ", str(text or "")).strip()


def _deduplicate_non_empty(values: list[str]) -> list[str]:
    """保序去重并丢弃空字符串。"""

    deduplicated: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = _compact_spaces(value)
        if not cleaned or cleaned in seen:
            continue
        deduplicated.append(cleaned)
        seen.add(cleaned)
    return deduplicated
