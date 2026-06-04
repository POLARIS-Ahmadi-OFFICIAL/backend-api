"""Format hypothesis agent output as separate chat bubbles (Streamlit-style)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _bubble(role: str, title: str, content: str) -> Dict[str, str]:
    return {
        "role": role,
        "title": title,
        "content": (content or "").strip(),
    }


def build_submit_bubbles(
    clarified: str,
    soc_pass: str,
    soc_answers: Optional[str],
    thoughts: List[str],
) -> List[Dict[str, str]]:
    """Mirror Streamlit: clarified → socratic pass → reasoning → three thoughts."""
    bubbles: List[Dict[str, str]] = []
    if clarified.strip():
        bubbles.append(_bubble("assistant", "Clarified question", clarified))
    if soc_pass.strip():
        bubbles.append(_bubble("assistant", "Socratic pass (probing questions)", soc_pass))
    if soc_answers and str(soc_answers).strip():
        bubbles.append(_bubble("assistant", "Socratic reasoning", str(soc_answers)))
    for i, thought in enumerate(thoughts[:3], 1):
        if thought and str(thought).strip():
            bubbles.append(_bubble("assistant", f"Generated thought {i}", str(thought).strip()))
    return bubbles


def build_choose_bubbles(
    picked: str,
    soc_q: str,
    options: List[str],
) -> List[Dict[str, str]]:
    """Mirror Streamlit refine step: selected option → continuation → next steps."""
    bubbles: List[Dict[str, str]] = []
    if picked and str(picked).strip():
        bubbles.append(_bubble("assistant", "Selected option", str(picked).strip()))
    q = (soc_q or "").strip()
    if not q or q.lower() == "none":
        q = "How can we continue exploring this hypothesis?"
    bubbles.append(_bubble("assistant", "Continuation question", q))
    lines = []
    for i, opt in enumerate(options[:3], 1):
        o = str(opt).strip() if opt else ""
        if not o or o.lower() == "none":
            o = f"Option {i}: Continue exploring this line of reasoning"
        lines.append(f"**{i}.** {o}")
    if lines:
        bubbles.append(_bubble("assistant", "Next-step options", "\n\n".join(lines)))
    return bubbles


def build_continue_bubbles(picked: str, options: List[str]) -> List[Dict[str, str]]:
    """Hypothesis-stage iteration: selected path → refreshed next-step options."""
    bubbles: List[Dict[str, str]] = []
    if picked and str(picked).strip():
        bubbles.append(_bubble("assistant", "Selected option", str(picked).strip()))
    lines = []
    for i, opt in enumerate(options[:3], 1):
        o = str(opt).strip() if opt else ""
        if not o or o.lower() == "none":
            o = f"Option {i}: Continue exploring this line of reasoning"
        lines.append(f"**{i}.** {o}")
    if lines:
        bubbles.append(_bubble("assistant", "Next-step options", "\n\n".join(lines)))
    return bubbles


def build_hypothesis_result_bubbles(hypothesis: str, analysis_rubric: Optional[str]) -> List[Dict[str, str]]:
    bubbles: List[Dict[str, str]] = []
    if hypothesis and str(hypothesis).strip():
        bubbles.append(_bubble("assistant", "Hypothesis", str(hypothesis).strip()))
    if analysis_rubric and str(analysis_rubric).strip():
        bubbles.append(_bubble("assistant", "Analysis report", str(analysis_rubric).strip()))
    return bubbles


def join_bubbles_for_legacy(bubbles: List[Dict[str, str]]) -> str:
    """Plain-text fallback for clients that only read assistant_message."""
    parts = []
    for b in bubbles:
        title = b.get("title") or ""
        content = b.get("content") or ""
        if title:
            parts.append(f"**{title}**\n\n{content}")
        else:
            parts.append(content)
    return "\n\n---\n\n".join(parts)
