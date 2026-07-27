"""程序说明：提供 LLM 客户端抽象，兼容 disabled、OpenAI 兼容接口与 Anthropic。"""

from __future__ import annotations

import json
import re

import httpx

from src.common.config import AppSettings
from src.common.errors import ExternalServiceAppError, ValidationAppError


DEFAULT_SYSTEM_PROMPT = """你是中文知识库质检助手。
请基于给定 claim、证据片段与规则命中结果，输出 JSON：
{
  "verdict": "verified|needs_review|rejected",
  "evidence_judgement": "support|contradict|insufficient",
  "confidence": 0.0,
  "risk_level": "low|medium|high",
  "reason": "简短中文原因"
}
要求：
1. 先判断证据对 claim 是 support、contradict 还是 insufficient，再给 verdict。
2. 没有足够证据时不要输出 verified；存在反证时优先输出 rejected。
3. 若 claim 含唯一化、绝对化、全称化、否定化限制，必须核对这些限制本身是否被证据直接支持。
4. 若证据同时存在支持与矛盾线索，优先判断是否已形成“证据冲突”或“覆盖不足”，不要只凭局部支持就输出 verified。
5. 命中高风险规则时，风险等级不能低于规则等级。
6. 只输出 JSON，不要输出额外说明。"""

DEFAULT_USER_PROMPT_TEMPLATE = """任务：请核验以下 claim 是否能被知识库证据支持。

Claim:
{claim_text}

证据：
{evidence_block}

逻辑约束：
{claim_logic_block}

规则命中：
{rule_block}

请严格返回 JSON，不要输出解释性段落。"""


class BaseLLMClient:
    """LLM 客户端抽象基类。"""

    def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict:
        """调用模型并要求返回 JSON 对象。"""

        raise NotImplementedError

    def evaluate_claim(
        self,
        *,
        claim_text: str,
        evidence_list: list[dict],
        matched_rules: list[dict],
        prompt_template: dict | None = None,
    ) -> dict:
        """基于证据评估 claim。"""

        raise NotImplementedError


class DisabledLLMClient(BaseLLMClient):
    """禁用状态占位客户端。"""

    def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict:
        """禁用状态下不应被调用。"""

        raise ValidationAppError("LLM 客户端已禁用")

    def evaluate_claim(
        self,
        *,
        claim_text: str,
        evidence_list: list[dict],
        matched_rules: list[dict],
        prompt_template: dict | None = None,
    ) -> dict:
        """禁用状态下不应被调用。"""

        raise ValidationAppError("LLM 客户端已禁用")


class OpenAICompatibleLLMClient(BaseLLMClient):
    """OpenAI 兼容聊天接口客户端。"""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: int,
        max_tokens: int,
        temperature: float,
        top_p: float,
        enable_thinking: bool,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.top_p = top_p
        self.enable_thinking = enable_thinking

    def evaluate_claim(
        self,
        *,
        claim_text: str,
        evidence_list: list[dict],
        matched_rules: list[dict],
        prompt_template: dict | None = None,
    ) -> dict:
        """调用 OpenAI 兼容聊天接口进行结构化判定。"""

        system_prompt, user_prompt = _build_quality_prompts(
            claim_text=claim_text,
            evidence_list=evidence_list,
            matched_rules=matched_rules,
            prompt_template=prompt_template,
        )
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": self.temperature,
                    "top_p": self.top_p,
                    "max_tokens": self.max_tokens,
                    "response_format": {"type": "json_object"},
                    # 兼容支持推理模式的 OpenAI 风格模型，默认关闭 thinking，避免占满输出配额。
                    "enable_thinking": self.enable_thinking,
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
            return _parse_llm_result(content)
        except Exception as exc:  # noqa: BLE001
            raise ExternalServiceAppError(
                "LLM 服务调用失败",
                details={"provider": "openai", "model": self.model},
            ) from exc

    def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict:
        """调用 OpenAI 兼容聊天接口，并解析 JSON 对象。"""

        try:
            return self._complete_json_once(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                use_response_format=True,
            )
        except Exception as exc:  # noqa: BLE001
            first_error = exc
        try:
            return self._complete_json_once(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                use_response_format=False,
            )
        except Exception as exc:  # noqa: BLE001
            raise ExternalServiceAppError(
                "LLM 服务调用失败",
                details={"provider": "openai", "model": self.model, "first_error": str(first_error)[:300]},
            ) from exc

    def _complete_json_once(self, *, system_prompt: str, user_prompt: str, use_response_format: bool) -> dict:
        """执行一次 OpenAI 兼容 JSON 调用；必要时允许从普通文本中提取 JSON。"""

        request_payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
            "enable_thinking": self.enable_thinking,
        }
        if use_response_format:
            request_payload["response_format"] = {"type": "json_object"}
        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=request_payload,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        content = payload["choices"][0]["message"]["content"]
        parsed = _parse_json_object(content)
        return parsed if isinstance(parsed, dict) else {}


class AnthropicLLMClient(BaseLLMClient):
    """Anthropic Messages 接口客户端。"""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: int,
        max_tokens: int,
        temperature: float,
        top_p: float,
        anthropic_version: str,
        base_url: str | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.top_p = top_p
        self.anthropic_version = anthropic_version
        self.base_url = (base_url or "https://api.anthropic.com").rstrip("/")

    def evaluate_claim(
        self,
        *,
        claim_text: str,
        evidence_list: list[dict],
        matched_rules: list[dict],
        prompt_template: dict | None = None,
    ) -> dict:
        """调用 Anthropic Messages 接口进行结构化判定。"""

        system_prompt, user_prompt = _build_quality_prompts(
            claim_text=claim_text,
            evidence_list=evidence_list,
            matched_rules=matched_rules,
            prompt_template=prompt_template,
        )
        try:
            response = httpx.post(
                f"{self.base_url}/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": self.anthropic_version,
                    "content-type": "application/json",
                },
                json={
                    "model": self.model,
                    "system": system_prompt,
                    "max_tokens": self.max_tokens,
                    "temperature": self.temperature,
                    "top_p": self.top_p,
                    "messages": [
                        {
                            "role": "user",
                            "content": [{"type": "text", "text": user_prompt}],
                        }
                    ],
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            content = payload["content"][0]["text"]
            return _parse_llm_result(content)
        except Exception as exc:  # noqa: BLE001
            raise ExternalServiceAppError(
                "LLM 服务调用失败",
                details={"provider": "anthropic", "model": self.model},
            ) from exc

    def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict:
        """调用 Anthropic Messages 接口，并解析 JSON 对象。"""

        try:
            response = httpx.post(
                f"{self.base_url}/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": self.anthropic_version,
                    "content-type": "application/json",
                },
                json={
                    "model": self.model,
                    "system": system_prompt,
                    "max_tokens": self.max_tokens,
                    "temperature": self.temperature,
                    "top_p": self.top_p,
                    "messages": [
                        {
                            "role": "user",
                            "content": [{"type": "text", "text": user_prompt}],
                        }
                    ],
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            content = payload["content"][0]["text"]
            parsed = json.loads(content)
            return parsed if isinstance(parsed, dict) else {}
        except Exception as exc:  # noqa: BLE001
            raise ExternalServiceAppError(
                "LLM 服务调用失败",
                details={"provider": "anthropic", "model": self.model},
            ) from exc


def build_llm_client(settings: AppSettings) -> BaseLLMClient:
    """根据配置构建 LLM 客户端。"""

    provider = settings.llm_provider.lower().strip()
    if provider in {"disabled", "none", ""}:
        return DisabledLLMClient()
    if not settings.llm_api_key:
        raise ValidationAppError("缺少 LLM_API_KEY", details={"provider": provider})
    if provider == "openai":
        return OpenAICompatibleLLMClient(
            base_url=settings.llm_base_url or "https://api.openai.com/v1",
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            timeout_seconds=settings.llm_timeout_seconds,
            max_tokens=settings.llm_max_tokens,
            temperature=settings.llm_temperature,
            top_p=settings.llm_top_p,
            enable_thinking=settings.llm_enable_thinking,
        )
    if provider == "anthropic":
        return AnthropicLLMClient(
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            timeout_seconds=settings.llm_timeout_seconds,
            max_tokens=settings.llm_max_tokens,
            temperature=settings.llm_temperature,
            top_p=settings.llm_top_p,
            anthropic_version=settings.anthropic_api_version,
            base_url=settings.llm_base_url,
        )
    raise ValidationAppError("不支持的 LLM_PROVIDER", details={"provider": settings.llm_provider})


def _build_quality_prompts(
    *,
    claim_text: str,
    evidence_list: list[dict],
    matched_rules: list[dict],
    prompt_template: dict | None = None,
) -> tuple[str, str]:
    """构建 system prompt 与 user prompt。"""

    resolved_template = prompt_template or {}
    system_prompt = resolved_template.get("system_prompt") or DEFAULT_SYSTEM_PROMPT
    user_prompt_template = resolved_template.get("user_prompt_template") or DEFAULT_USER_PROMPT_TEMPLATE
    claim_logic = _build_claim_logic_block(claim_text)
    evidence_lines = [
        (
            f'- 文档: {item.get("doc_uid")} | 位置: {item.get("source_span")} | '
            f'查询来源: {"/".join(item.get("matched_queries", [])) or "-"} | '
            f'证据关系: {item.get("evidence_relation") or "-"} | '
            f'关系说明: {item.get("relation_reason") or "-"} | '
            f'内容: {str(item.get("expanded_content") or item.get("content") or "")[:400]}'
        )
        for item in evidence_list
    ] or ["- 无证据"]
    rule_lines = [
        f'- 规则: {item.get("rule_code")} | 等级: {item.get("hit_level")} | 原因: {item.get("hit_message")}'
        for item in matched_rules
    ] or ["- 无规则命中"]
    # M5 修复：使用 try/except 防止自定义模板中的花括号导致崩溃
    try:
        user_prompt = user_prompt_template.format(
            claim_text=claim_text,
            evidence_block="\n".join(evidence_lines),
            claim_logic_block=claim_logic,
            rule_block="\n".join(rule_lines),
        )
    except (KeyError, ValueError, IndexError):
        # 模板中包含未转义的花括号时，回退到默认模板
        user_prompt = DEFAULT_USER_PROMPT_TEMPLATE.format(
            claim_text=claim_text,
            evidence_block="\n".join(evidence_lines),
            claim_logic_block=claim_logic,
            rule_block="\n".join(rule_lines),
        )
    return system_prompt, user_prompt


# C3 修复：合法枚举白名单，防止 LLM 返回非法值污染数据库
_VALID_VERDICTS = {"verified", "needs_review", "rejected"}
_VALID_JUDGEMENTS = {"support", "contradict", "insufficient"}
_VALID_RISK_LEVELS = {"low", "medium", "high"}


def _parse_llm_result(content: str) -> dict:
    """解析 LLM 返回的 JSON 结果，并校验枚举值和范围约束。"""

    payload = _parse_json_object(content)
    if "verdict" not in payload and isinstance(payload.get("interpretation"), dict):
        payload = payload["interpretation"]
    # 枚举校验：非法值回退到安全默认值
    verdict = str(payload.get("verdict", "needs_review"))
    if verdict not in _VALID_VERDICTS:
        verdict = "needs_review"
    evidence_judgement = str(payload.get("evidence_judgement", "insufficient"))
    if evidence_judgement not in _VALID_JUDGEMENTS:
        evidence_judgement = "insufficient"
    risk_level = str(payload.get("risk_level", "medium"))
    if risk_level not in _VALID_RISK_LEVELS:
        risk_level = "medium"
    # confidence 范围约束 [0.0, 1.0]
    try:
        confidence = max(0.0, min(1.0, float(payload.get("confidence", 0.2))))
    except (TypeError, ValueError):
        confidence = 0.2
    return {
        "verdict": verdict,
        "evidence_judgement": evidence_judgement,
        "confidence": confidence,
        "risk_level": risk_level,
        "reason": str(payload.get("reason", "")),
    }


def _parse_json_object(content: str) -> dict:
    """从模型输出中解析 JSON 对象，兼容前后带解释文字的响应。"""

    text = str(content or "").strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise
        payload = json.loads(match.group(0))
    if not isinstance(payload, dict):
        raise ValueError("LLM 返回内容不是 JSON 对象")
    return payload


def _build_claim_logic_block(claim_text: str) -> str:
    """提炼 claim 中的逻辑约束，提醒模型重点核对限制条件。"""

    text = str(claim_text or "")
    logic_labels: list[str] = []
    if any(marker in text for marker in ("只有", "唯一", "仅有", "仅限", "独家")):
        logic_labels.append("唯一化/排他性表述")
    if any(
        marker in text
        for marker in (
            "全部",
            "所有",
            "一律",
            "必然",
            "总是",
            "完全",
            "任何",
            "绝对",
            "一定",
            "必定",
            "无论",
            "不限量",
        )
    ):
        logic_labels.append("全称或绝对化表述")
    boundary_markers = (
        "不能随意",
        "不能替代",
        "不能直接",
        "不能作为",
        "不能证明",
        "不是唯一",
        "并非唯一",
        "不能治疗所有",
        "不是所有",
        "需结合",
        "应结合",
    )
    evidence_gap_markers = ("没有证据", "无证据", "缺乏证据", "尚无证据", "未见明确")
    if any(marker in text for marker in boundary_markers):
        logic_labels.append("安全边界或限制性表述（不能将否定词误判为反证）")
    elif any(marker in text for marker in evidence_gap_markers):
        logic_labels.append("证据缺口表述（应输出未知或需复核）")
    elif any(marker in text for marker in ("不会", "不能", "没有", "不存在", "绝不", "从不")):
        logic_labels.append("否定性表述")
    # L1 修复：增加比较型检测
    if any(marker in text for marker in ("高于", "低于", "强于", "弱于", "优于", "不如", "最多", "最少", "超过", "不少于", "不低于")):
        logic_labels.append("比较型表述")
    if not logic_labels:
        logic_labels.append("普通事实陈述")

    normalized = text
    for marker in ("只有", "唯一", "仅有", "仅限", "独家", "全部", "所有", "一律", "必然", "总是", "完全", "不会", "不能", "没有", "不存在", "绝不", "从不"):
        normalized = normalized.replace(marker, " ")
    normalized = re.sub(r"[，。！？；：、“”‘’\"'（）()\[\]{}<>《》]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return f'- 识别结果：{"、".join(logic_labels)}\n- 放宽检索主题：{normalized or text}'
