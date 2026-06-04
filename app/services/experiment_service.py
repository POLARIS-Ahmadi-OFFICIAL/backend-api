"""Headless experiment agent pipeline (mirrors Streamlit pages/experiment.py + run_agent)."""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional

from app.services.document_export import export_agent_document
from app.services.jupyter_upload import get_jupyter_config, upload_with_memory_config
from app.services.experiment_defaults import (
    EQUIPMENT_OPTIONS,
    FOCUS_AREA_OPTIONS,
    INSTRUMENT_OPTIONS,
    PARAMETER_OPTIONS,
    PLATE_FORMAT_OPTIONS,
    PRESET_MATERIALS,
    TECHNIQUE_OPTIONS,
    merge_constraints,
)
from app.services.llm_runtime import require_api_key
from app.tools import socratic


def _manual_inputs(memory: Any) -> Dict[str, str]:
    return {
        "manual_clarified_question": str(memory.get_var("manual_clarified_question") or ""),
        "manual_socratic_questions": str(memory.get_var("manual_socratic_questions") or ""),
        "manual_socratic_answers": str(memory.get_var("manual_socratic_answers") or ""),
        "manual_thoughts": str(memory.get_var("manual_thoughts") or ""),
        "manual_hypothesis": str(memory.get_var("manual_hypothesis") or ""),
    }


def patch_manual_inputs(memory: Any, data: Dict[str, Any]) -> None:
    for key in _manual_inputs(memory).keys():
        if key in data and data[key] is not None:
            memory.set_var(key, str(data[key]))


def _analysis_context(memory: Any) -> Dict[str, Any]:
    return {
        "analysis_full_report": memory.get_var("analysis_full_report") or "",
        "analysis_recommendations": memory.get_var("analysis_recommendations") or [],
        "gp_suggested_compositions": memory.get_var("gp_suggested_compositions") or [],
    }


def _readiness(memory: Any) -> Dict[str, Any]:
    clarified = memory.view_component("clarified_question") or memory.get_var("manual_clarified_question") or ""
    socratic_q = memory.view_component("socratic_pass") or memory.get_var("manual_socratic_questions") or ""
    hypothesis = memory.view_component("hypothesis") or memory.get_var("manual_hypothesis") or memory.get_var("last_hypothesis") or ""
    return {
        "clarified_question": str(clarified).strip(),
        "socratic_questions": str(socratic_q).strip(),
        "hypothesis": str(hypothesis).strip(),
        "clarified_source": "memory" if memory.view_component("clarified_question") else ("manual" if memory.get_var("manual_clarified_question") else "missing"),
        "socratic_source": "memory" if memory.view_component("socratic_pass") else ("manual" if memory.get_var("manual_socratic_questions") else "missing"),
        "hypothesis_source": "memory" if memory.view_component("hypothesis") else ("manual" if memory.get_var("manual_hypothesis") else "missing"),
        "ready_to_run": bool(str(clarified).strip() and str(socratic_q).strip()),
    }


def get_experiment_option_lists() -> Dict[str, List[str]]:
    return {
        "techniques": TECHNIQUE_OPTIONS,
        "equipment": EQUIPMENT_OPTIONS,
        "instruments": INSTRUMENT_OPTIONS,
        "plate_formats": PLATE_FORMAT_OPTIONS,
        "parameters": PARAMETER_OPTIONS,
        "focus_areas": FOCUS_AREA_OPTIONS,
        "preset_materials": PRESET_MATERIALS,
    }


def get_experiment_session(memory: Any) -> Dict[str, Any]:
    outputs = memory.get_var("experimental_outputs")
    last_doc = memory.get_var("document_experiment") or {}
    doc_meta = {}
    if isinstance(last_doc, dict) and last_doc.get("document_id"):
        doc_meta = {
            "document_id": last_doc.get("document_id"),
            "document_markdown": last_doc.get("markdown"),
            "pdf_url": last_doc.get("pdf_url"),
        }
    return {
        "experimental_constraints": merge_constraints(memory.get_var("experimental_constraints")),
        "manual_inputs": _manual_inputs(memory),
        "readiness": _readiness(memory),
        "analysis_context": _analysis_context(memory),
        "experimental_outputs": outputs if isinstance(outputs, dict) else None,
        "has_experimental_plan": bool(memory.view_component("experimental_plan")),
        "api_key_configured": bool(memory.get_var("api_key")),
        "option_lists": get_experiment_option_lists(),
        "jupyter_config": get_jupyter_config(memory),
        **doc_meta,
    }


def patch_experiment_session(
    memory: Any,
    *,
    experimental_constraints: Optional[Dict[str, Any]] = None,
    manual_inputs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if experimental_constraints is not None:
        memory.set_var("experimental_constraints", merge_constraints(experimental_constraints))
    if manual_inputs is not None:
        patch_manual_inputs(memory, manual_inputs)
    return get_experiment_session(memory)


def _protocol_markdown(plan: str, worklist: str, layout: str, protocol: Optional[str]) -> str:
    parts = [
        "# Experimental Protocol\n",
        "## Experimental plan\n",
        str(plan).strip(),
        "\n\n## Worklist (CSV)\n",
        "```csv\n",
        str(worklist).strip(),
        "\n```\n",
        "\n## Plate layout\n",
        "```\n",
        str(layout).strip(),
        "\n```\n",
    ]
    if protocol and str(protocol).strip():
        parts.extend(["\n## Opentrons protocol\n", "```python\n", str(protocol).strip(), "\n```\n"])
    return "".join(parts)


def upload_experiment_artifact_to_jupyter(memory: Any, *, artifact: str = "worklist") -> Dict[str, Any]:
    """Upload worklist, GP worklist, or Opentrons protocol from session outputs."""
    outputs = memory.get_var("experimental_outputs") or {}
    if not isinstance(outputs, dict):
        outputs = {}

    filename_map = {
        "worklist": ("worklist", "worklist.csv"),
        "gp_worklist": ("gp_worklist", "gp_suggested_compositions_worklist.csv"),
        "protocol": ("protocol", "opentrons_protocol.py"),
    }
    if artifact not in filename_map:
        return {"status": "error", "message": f"Unknown artifact: {artifact}"}

    key, filename = filename_map[artifact]
    content = outputs.get(key)
    if not content or not str(content).strip():
        return {"status": "error", "message": f"No {artifact} in session. Run the experiment agent or generate a GP worklist first."}

    jupyter_result = upload_with_memory_config(memory, str(content), filename)
    status = "success" if jupyter_result.get("success") else "error"
    return {
        "status": status,
        "message": jupyter_result.get("message", ""),
        "jupyter_upload": jupyter_result,
        "artifact": artifact,
        "filename": filename,
    }


def generate_gp_worklist(memory: Any, *, upload_to_jupyter: bool = False) -> Dict[str, Any]:
    gp = memory.get_var("gp_suggested_compositions") or []
    if not gp:
        return {"status": "error", "message": "No GP suggested compositions in session."}
    constraints = merge_constraints(memory.get_var("experimental_constraints"))
    max_vol = int(constraints["liquid_handling"]["max_volume_per_mixture"])
    materials = list(gp[0].get("compositions", {}).keys()) if gp else []
    if not materials:
        return {"status": "error", "message": "No composition keys in GP suggestions."}

    import csv
    import io

    wells = [f"A{i + 1:02d}" for i in range(min(len(gp), 12))]
    rows: List[Dict[str, Any]] = []
    for i, sc in enumerate(gp[:12]):
        comp = sc.get("compositions", {})
        row: Dict[str, Any] = {"Well": wells[i]}
        total = sum(abs(float(v)) for v in comp.values()) or 1.0
        for m in materials:
            frac = abs(float(comp.get(m, 0))) / total
            row[f"{m}_uL"] = round(frac * max_vol, 1)
        rows.append(row)

    buf = io.StringIO()
    fieldnames = ["Well"] + [f"{m}_uL" for m in materials]
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    csv_content = buf.getvalue()

    outputs = memory.get_var("experimental_outputs") or {}
    if not isinstance(outputs, dict):
        outputs = {}
    outputs["gp_worklist"] = csv_content
    memory.set_var("experimental_outputs", outputs)

    result: Dict[str, Any] = {
        "status": "success",
        "message": "Worklist generated from GP compositions.",
        "worklist_csv": csv_content,
    }
    if upload_to_jupyter:
        jupyter_result = upload_with_memory_config(
            memory,
            csv_content,
            "gp_suggested_compositions_worklist.csv",
        )
        result["jupyter_upload"] = jupyter_result
        if jupyter_result.get("success"):
            result["message"] = jupyter_result.get("message", result["message"])
        else:
            result["status"] = "error"
            result["message"] = jupyter_result.get("message", "Jupyter upload failed.")
    return result


def run_experiment_pipeline(memory: Any) -> Dict[str, Any]:
    """Full Streamlit run_agent flow without UI."""
    require_api_key(memory)

    readiness = _readiness(memory)
    if not readiness["ready_to_run"]:
        return {
            "status": "error",
            "message": "Missing required inputs: clarified question and Socratic questions (from Hypothesis agent or Manual Input).",
            "readiness": readiness,
        }

    counts = memory.get_var("agent_usage_counts") or {}
    if not isinstance(counts, dict):
        counts = {}
    counts["experiment"] = int(counts.get("experiment", 0)) + 1
    memory.set_var("agent_usage_counts", counts)
    memory.snapshot_session_state("before_experiment_agent_run")

    from app.agents.experiment_agent import ExperimentAgent

    constraints = merge_constraints(memory.get_var("experimental_constraints"))
    memory.set_var("experimental_constraints", constraints)

    agent = ExperimentAgent(
        name="Experiment Agent",
        desc="Generates experimental plans and automation artifacts.",
        params_const=constraints,
    )
    agent.memory = memory

    clarified = readiness["clarified_question"] or "How can we test this research question?"
    socratic_q = readiness["socratic_questions"] or "What experimental approaches are needed?"
    hypothesis = readiness["hypothesis"]

    if memory.get_var("manual_clarified_question"):
        memory.insert_interaction("user", memory.get_var("manual_clarified_question"), "clarified_question", "experiment")
    if memory.get_var("manual_socratic_questions"):
        memory.insert_interaction("assistant", memory.get_var("manual_socratic_questions"), "socratic_pass", "experiment")
    if memory.get_var("manual_socratic_answers"):
        memory.insert_interaction("assistant", memory.get_var("manual_socratic_answers"), "socratic_answers", "experiment")
    if memory.get_var("manual_hypothesis"):
        memory.insert_interaction("assistant", memory.get_var("manual_hypothesis"), "hypothesis", "experiment")
        hypothesis = str(memory.get_var("manual_hypothesis"))

    experimental_context = agent.get_experimental_context()
    plans = socratic.tot_generation_experimental_plan(socratic_q, clarified, experimental_context)
    if not plans:
        return {
            "status": "error",
            "message": "Failed to generate experimental plans. Check API key.",
            "readiness": readiness,
        }

    plan = plans[0] if plans[0] else (hypothesis or "")
    memory.insert_interaction("assistant", plan, "experimental_plan", "experiment")

    lh = constraints["liquid_handling"]
    plate_format = lh["plate_format"]
    materials = lh["materials"] or ["Cs", "BDA"]
    csv_materials = [m if str(m).endswith("_uL") else f"{m}_uL" for m in materials]

    worklist = agent.generate_worklist(plan, plate_format, csv_materials)
    layout = agent.generate_plate_layout(plan, plate_format, worklist)
    protocol = None
    if any("Opentrons" in str(i) for i in lh.get("instruments") or []):
        protocol = agent.generate_opentrons_protocol("worklist.csv", csv_materials, lh.get("csv_path") or "")

    memory.set_var(
        "experimental_outputs",
        {"plan": plan, "worklist": worklist, "layout": layout, "protocol": protocol},
    )

    protocol_md = _protocol_markdown(plan, worklist, layout, protocol)
    doc = export_agent_document(
        title="Experimental Protocol",
        markdown_body=protocol_md,
        agent="experiment",
        memory=memory,
    )

    try:
        from app.tools.experiment_memory import get_experiment_memory

        experiment_memory = get_experiment_memory(memory)
        worklist_hash = hashlib.md5(worklist.encode()).hexdigest()[:8]
        exp_id = f"exp_{worklist_hash}"
        composition = {mat: 0 for mat in materials} if materials else {}
        if not experiment_memory.has_experiment(exp_id):
            experiment_memory.add_experiment(
                experiment_id=exp_id,
                description=f"Experimental plan: {str(plan)[:200]}...",
                composition=composition,
                metadata={
                    "plate_format": plate_format,
                    "materials": materials,
                    "plan_length": len(str(plan)),
                },
            )
    except Exception:
        pass

    memory.log_event(
        "experiment_complete",
        {"plan": str(plan)[:500], "plate_format": plate_format, "materials": materials},
        "experiment",
    )

    return {
        "status": "success",
        "message": "Experimental protocol generated (plan, worklist, plate layout).",
        "readiness": readiness,
        "experimental_plan_preview": str(plan)[:1500],
        "protocol_markdown": protocol_md,
        "worklist_csv": worklist,
        "plate_layout": layout,
        "opentrons_protocol": protocol,
        "plate_format": plate_format,
        "materials": materials,
        "document_id": doc["document_id"],
        "document_markdown": doc["markdown"],
        "pdf_url": doc["pdf_url"],
        "has_experimental_plan": True,
    }
