"""Analysis Agent page session — parity with Streamlit pages/analysis.py."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

from app.services.curve_fitting_service import serialize_curve_fitting_results
from app.services.llm_runtime import require_api_key
from app.tools.paths import get_results_dir
from app.utils.json_safe import to_jsonable


def _hypothesis_preview(memory: Any) -> Optional[str]:
    hyp = memory.view_component("hypothesis") or memory.get_var("last_hypothesis")
    if hyp and str(hyp).strip():
        text = str(hyp).strip()
        return text[:500] + ("…" if len(text) > 500 else "")
    return None


def _load_curve_fitting_results(memory: Any) -> Optional[Dict[str, Any]]:
    raw = memory.get_var("curve_fitting_results")
    if isinstance(raw, dict):
        if raw.get("wells"):
            return raw
        if raw.get("results"):
            return serialize_curve_fitting_results(raw) or raw

    results_dir = get_results_dir()
    if not os.path.isdir(results_dir):
        return None
    json_files = [f for f in os.listdir(results_dir) if f.endswith("_peak_fit_results.json")]
    if not json_files:
        return None
    latest = max(json_files, key=lambda f: os.path.getmtime(os.path.join(results_dir, f)))
    path = os.path.join(results_dir, latest)
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _summarize_curve_fitting(results: Dict[str, Any]) -> str:
    if not isinstance(results, dict):
        return "No curve fitting results available."

    parts: list[str] = []

    if "wells" in results and isinstance(results["wells"], list):
        wells = results["wells"]
        successful = sum(1 for w in wells if (w.get("fit") or {}).get("success"))
        parts.append(f"**Total Wells Analyzed:** {len(wells)}")
        parts.append(f"**Successful Fits:** {successful}/{len(wells)}")
        for w in wells[:10]:
            fit = w.get("fit") or {}
            if fit.get("success"):
                peaks = fit.get("peaks") or []
                centers = [p.get("center") for p in peaks[:3] if p.get("center") is not None]
                r2 = fit.get("r2")
                label = f"{w.get('well_name', '?')}"
                if w.get("read"):
                    label += f" (Read {w['read']})"
                peak_str = ", ".join(f"{c:.1f}nm" for c in centers) if centers else "n/a"
                parts.append(f"  - {label}: R²={r2:.3f}, peaks at {peak_str}" if r2 is not None else f"  - {label}: peaks at {peak_str}")
        return "\n".join(parts)

    if "wells" in results and isinstance(results["wells"], dict):
        wells_dict = results["wells"]
        parts.append(f"**Total Wells:** {len(wells_dict)}")
        for name, data in list(wells_dict.items())[:8]:
            fr = (data or {}).get("fitting_results") or {}
            qm = fr.get("quality_metrics") or {}
            parts.append(f"  - {name}: R²={qm.get('r_squared', 'n/a')}")
        return "\n".join(parts)

    summary = results.get("summary")
    if isinstance(summary, dict):
        parts.append(
            f"**Summary:** {summary.get('successful_fits', 0)}/{summary.get('total_wells', 0)} successful fits"
        )
    return "\n".join(parts) if parts else "Curve fitting results loaded (see JSON for details)."


def get_analysis_session(memory: Any) -> Dict[str, Any]:
    hypothesis_ctx = ""
    hyp = memory.view_component("hypothesis") or memory.get_var("last_hypothesis")
    if hyp:
        hypothesis_ctx += f"**Hypothesis:**\n{hyp}\n"
    clarified = memory.view_component("clarified_question")
    if clarified:
        hypothesis_ctx += f"**Research Question:**\n{clarified}\n"
    socratic = memory.view_component("socratic_pass")
    if socratic:
        hypothesis_ctx += f"**Socratic Analysis:**\n{socratic}\n"

    exp_out = memory.get_var("experimental_outputs") or {}
    exp_ctx = ""
    if isinstance(exp_out, dict):
        if exp_out.get("plan"):
            exp_ctx += f"**Experimental Plan:**\n{exp_out['plan']}\n"
        if exp_out.get("worklist"):
            wl = str(exp_out["worklist"])
            exp_ctx += f"**Worklist:**\n{wl[:500]}{'…' if len(wl) > 500 else ''}\n"

    curve = _load_curve_fitting_results(memory)
    gp_results = memory.get_var("gp_results")
    mc_results = memory.get_var("monte_carlo_results")
    full_report = memory.get_var("analysis_full_report") or memory.view_component("analysis_rubric")
    recommendations = memory.get_var("analysis_recommendations")

    return to_jsonable(
        {
            "research_goal": memory.get_var("research_goal") or "",
            "hypothesis_context": hypothesis_ctx.strip() or "No hypothesis context available.",
            "experimental_context": exp_ctx.strip() or "No experimental data available.",
            "has_curve_fitting": curve is not None,
            "curve_fitting_summary": _summarize_curve_fitting(curve) if curve else None,
            "has_gp_results": bool(gp_results),
            "gp_results": gp_results if isinstance(gp_results, dict) else None,
            "monte_carlo_results": mc_results if isinstance(mc_results, dict) else None,
            "has_hypothesis": bool(_hypothesis_preview(memory)),
            "hypothesis_preview": _hypothesis_preview(memory),
            "analysis_full_report": str(full_report) if full_report else None,
            "analysis_recommendations": recommendations,
            "ready": bool(_hypothesis_preview(memory)),
        }
    )


def patch_analysis_session(memory: Any, *, research_goal: Optional[str] = None) -> Dict[str, Any]:
    if research_goal is not None:
        memory.set_var("research_goal", research_goal)
    return get_analysis_session(memory)


def run_analysis_pipeline(memory: Any, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload = payload or {}
    if payload.get("research_goal"):
        memory.set_var("research_goal", payload["research_goal"])

    session = get_analysis_session(memory)
    if not session.get("has_hypothesis"):
        return {"status": "error", "message": "Generate a hypothesis first (Hypothesis agent).", "session": session}

    curve = _load_curve_fitting_results(memory)
    if not curve and not payload.get("skip_curve_check"):
        return {
            "status": "error",
            "message": "No curve fitting results found. Run Curve Fitting first or upload results JSON.",
            "session": session,
        }

    try:
        require_api_key(memory)
    except ValueError as exc:
        return {"status": "error", "message": str(exc), "session": session}

    from app.agents.analysis_agent import AnalysisAgent

    agent = AnalysisAgent()
    agent.memory = memory

    hypothesis_context = agent._get_hypothesis_context()
    experimental_context = agent._get_experimental_context()
    curve_summary = _summarize_curve_fitting(curve) if curve else "No curve fitting data."
    gp_results = agent._get_gp_results()
    monte_carlo_results = memory.get_var("monte_carlo_results")

    gp_summary = agent._summarize_gp_results(gp_results) if gp_results else ""
    mc_summary = ""
    if monte_carlo_results:
        mc_summary = agent._summarize_monte_carlo_results(monte_carlo_results)

    combined_summary = curve_summary
    if gp_summary:
        combined_summary += f"\n\n## ML (GP)\n{gp_summary}"
    if mc_summary:
        combined_summary += f"\n\n## ML (Monte Carlo)\n{mc_summary}"

    result = agent._analyze_results_with_llm(
        hypothesis_context,
        experimental_context,
        combined_summary,
        curve,
        gp_results,
        monte_carlo_results,
    )

    if not result.get("success"):
        return {
            "status": "error",
            "message": result.get("error") or "Analysis failed.",
            "session": get_analysis_session(memory),
        }

    analysis_text = result.get("analysis") or ""
    parsed = agent._parse_analysis_response(analysis_text)
    memory.insert_interaction("assistant", analysis_text, "analysis_rubric", "analysis")
    memory.set_var("analysis_full_report", analysis_text)
    memory.set_var("analysis_results", {"preview": analysis_text[:2000], "parsed": parsed})
    memory.set_var("analysis_recommendations", parsed.get("recommendations"))
    memory.set_var("analysis_ready", True)

    return to_jsonable(
        {
            "status": "success",
            "message": "Analysis report generated.",
            "analysis_report": analysis_text,
            "parsed": parsed,
            "session": get_analysis_session(memory),
        }
    )
