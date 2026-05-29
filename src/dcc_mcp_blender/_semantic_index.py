"""Optional morphology-aware semantic skill recall for Blender.

Ports :mod:`dcc_mcp_maya._semantic_index`.  ``BlenderMcpServer.search_skills``
routes through the Rust BM25-lite scorer in ``dcc-mcp-skills``, which misses
morphology variants a natural-language agent commonly produces (``"rendering
the active frame"`` does not tokenise to the literal ``render`` token).

This module fuses the Python-side ``VectorSkillIndex`` (``HashedEmbedder``
char-3-gram defaults, zero runtime deps) with a ``LexicalSkillIndex`` through
``RrfFusionIndex``.  The fused index is used **only to augment** the canonical
base results: base ordering is preserved verbatim and vector-only recalls are
appended afterwards.

Unlike the Maya port, Blender's ``search_skills`` / ``list_skills`` return
plain dicts, so the helpers below accept either dicts or attribute objects.

Gated behind ``DCC_MCP_BLENDER_SEMANTIC_INDEX=1`` (default off).  When the
optional ``dcc-mcp-core[semantic]`` extra is installed,
``DCC_MCP_BLENDER_SEMANTIC_EMBEDDER=onnx`` swaps in the dense ``OnnxEmbedder``.
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional, Sequence

from dcc_mcp_blender import _env

logger = logging.getLogger(__name__)

ENV_SEMANTIC_INDEX = _env.ENV_SEMANTIC_INDEX
ENV_SEMANTIC_EMBEDDER = _env.ENV_SEMANTIC_EMBEDDER


def resolve_semantic_index_enabled(env: Optional[dict] = None) -> bool:
    """Return ``True`` when ``DCC_MCP_BLENDER_SEMANTIC_INDEX`` is truthy."""
    return _env.resolve_semantic_index_enabled(env)


def resolve_embedder_kind(env: Optional[dict] = None) -> str:
    """Return the requested embedder kind: ``"hashed"`` (default) or ``"onnx"``."""
    return _env.resolve_semantic_embedder_kind(env)


def _get(summary: Any, key: str, default: Any = None) -> Any:
    """Read *key* from a dict or attribute object summary."""
    if isinstance(summary, dict):
        return summary.get(key, default)
    return getattr(summary, key, default)


def _summary_text(summary: Any) -> str:
    """Best-effort description string from a summary dict / object."""
    parts: List[str] = []
    for key in ("description", "search_hint"):
        value = _get(summary, key, "") or ""
        if value and str(value) not in parts:
            parts.append(str(value))
    return " ".join(parts)


def _summary_name(summary: Any) -> Optional[str]:
    name = _get(summary, "name", None) or _get(summary, "skill_name", None)
    return str(name) if name else None


def _summary_tags(summary: Any) -> tuple:
    tags = _get(summary, "tags", None) or ()
    return tuple(str(t) for t in tags)


def _summary_dcc(summary: Any) -> str:
    return str(_get(summary, "dcc", "") or _get(summary, "dcc_name", "") or "")


def _build_embedder(kind: str) -> Any:
    """Construct the requested embedder, falling back to ``HashedEmbedder``."""
    from dcc_mcp_core import HashedEmbedder  # noqa: PLC0415

    if kind != "onnx":
        return HashedEmbedder()
    try:
        from dcc_mcp_core import OnnxEmbedder  # noqa: PLC0415

        return OnnxEmbedder()
    except Exception as exc:  # noqa: BLE001 — EmbedderError / ImportError
        logger.warning(
            "[blender] DCC_MCP_BLENDER_SEMANTIC_EMBEDDER=onnx requested but unavailable "
            "(%s); falling back to HashedEmbedder. Install dcc-mcp-core[semantic].",
            exc,
        )
        return HashedEmbedder()


class BlenderSemanticIndex:
    """Lexical + vector fusion index used to augment base ``search_skills``."""

    def __init__(self, fusion: Any, embedder_kind: str) -> None:
        self._fusion = fusion
        self.embedder_kind = embedder_kind
        self._signature: Optional[frozenset] = None

    # ── construction ────────────────────────────────────────────────────
    @classmethod
    def build(cls, *, embedder_kind: Optional[str] = None) -> Optional["BlenderSemanticIndex"]:
        """Build the fused index, or ``None`` when core lacks the semantic API."""
        try:
            from dcc_mcp_core import LexicalSkillIndex, RrfFusionIndex, VectorSkillIndex  # noqa: PLC0415
        except Exception as exc:  # noqa: BLE001 — older core without the vector API
            logger.info(
                "[blender] semantic index requested but dcc-mcp-core lacks "
                "VectorSkillIndex (%s); needs dcc-mcp-core>=0.17.38.",
                exc,
            )
            return None
        kind = embedder_kind or resolve_embedder_kind()
        try:
            fusion = (
                RrfFusionIndex()
                .register("lex", LexicalSkillIndex())
                .register("vec", VectorSkillIndex(embedder=_build_embedder(kind)))
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[blender] failed to build semantic fusion index: %s", exc)
            return None
        return cls(fusion, kind)

    # ── indexing / recall ───────────────────────────────────────────────
    def rebuild(self, summaries: Sequence[Any]) -> None:
        """(Re)index ``summaries`` only when the skill set changed."""
        from dcc_mcp_core import SkillDocument  # noqa: PLC0415

        signature = frozenset(
            (name, str(_get(s, "version", "") or ""))
            for s, name in ((s, _summary_name(s)) for s in summaries)
            if name is not None
        )
        if signature == self._signature:
            return
        docs = []
        for summary in summaries:
            name = _summary_name(summary)
            if name is None:
                continue
            docs.append(
                SkillDocument(
                    skill_id=name,
                    name=name,
                    summary=_summary_text(summary),
                    tags=_summary_tags(summary),
                    dcc_name=_summary_dcc(summary),
                )
            )
        self._fusion.clear()
        if docs:
            self._fusion.index(docs)
        self._signature = signature

    def recall(self, query: str, *, k: int = 16) -> List[str]:
        """Return fused-rank ``skill_id``s for ``query`` (best first)."""
        if not query or not str(query).strip():
            return []
        try:
            hits = self._fusion.search(str(query), k=k)
        except Exception as exc:  # noqa: BLE001
            logger.debug("[blender] semantic recall failed for %r: %s", query, exc)
            return []
        return [hit.skill_id for hit in hits]

    # ── fusion / augmentation ───────────────────────────────────────────
    def augment(
        self,
        base: Sequence[Any],
        query: Optional[str],
        all_summaries: Sequence[Any],
        *,
        limit: Optional[int] = None,
    ) -> List[Any]:
        """Append morphology-recalled skills after the canonical ``base`` list.

        ``base`` ordering is preserved verbatim — RRF promotes, never demotes.
        Skills surfaced only by the vector backend are appended in fused-rank
        order.
        """
        result = list(base)
        if not query or not str(query).strip():
            return result
        try:
            self.rebuild(all_summaries)
        except Exception as exc:  # noqa: BLE001
            logger.debug("[blender] semantic rebuild failed: %s", exc)
            return result

        by_name = {name: s for s, name in ((s, _summary_name(s)) for s in all_summaries) if name is not None}
        present = {_summary_name(s) for s in result}
        for skill_id in self.recall(query):
            if skill_id in present or skill_id not in by_name:
                continue
            result.append(by_name[skill_id])
            present.add(skill_id)

        if limit is not None and limit >= 0:
            result = result[:limit]
        return result


def build_semantic_index() -> Optional[BlenderSemanticIndex]:
    """Return a ready index when the feature is enabled, else ``None``."""
    if not resolve_semantic_index_enabled():
        return None
    return BlenderSemanticIndex.build()
