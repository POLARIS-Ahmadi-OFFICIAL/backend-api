"""Dashboard payload aligned with Streamlit pages/dashboard.py."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Dict, List, Optional


def _count_events_by_mode(events: List[dict], mode_name: str) -> int:
    return len([e for e in events if (e.get("mode") or "").lower() == mode_name.lower()])


def _count_events_by_type(events: List[dict], type_name: str) -> int:
    return len([e for e in events if (e.get("type") or "").lower() == type_name.lower()])


def build_dashboard_detail(memory: Any) -> Dict[str, Any]:
    import psutil

    events = memory.get_var("conversation_events") or []
    if not isinstance(events, list):
        events = []

    metrics_prev = memory.get_var("metrics_prev") or {}
    if not isinstance(metrics_prev, dict):
        metrics_prev = {}

    current_cpu = psutil.cpu_percent(interval=0.1)
    cpu_delta = current_cpu - float(metrics_prev.get("prev_cpu", current_cpu))
    ram = psutil.virtual_memory()
    ram_delta = ram.percent - float(metrics_prev.get("ram", ram.percent))

    disk_percent = None
    try:
        disk = psutil.disk_usage("/")
        disk_percent = (disk.used / disk.total) * 100
    except Exception:
        pass

    start_time = memory.get_var("start_time") or time.time()
    if not memory.get_var("start_time"):
        memory.set_var("start_time", start_time)
    uptime = int(time.time() - float(start_time))
    uptime_delta = uptime - int(metrics_prev.get("uptime", uptime))
    uptime_hours = uptime // 3600
    uptime_mins = (uptime % 3600) // 60

    total_events = len(events)
    events_delta = total_events - int(metrics_prev.get("events", total_events))

    metrics_prev.update(
        {
            "prev_cpu": current_cpu,
            "ram": ram.percent,
            "uptime": uptime,
            "events": total_events,
        }
    )
    memory.set_var("metrics_prev", metrics_prev)

    usage = memory.get_var("agent_usage_counts") or {}
    if not isinstance(usage, dict):
        usage = {}
    total_agent_usage = sum(int(v) for v in usage.values())

    agent_usage_list = []
    for agent, count in usage.items():
        c = int(count)
        agent_usage_list.append(
            {
                "agent": agent,
                "label": agent.replace("_", " ").title(),
                "count": c,
                "percent": round(100.0 * c / total_agent_usage, 1) if total_agent_usage else 0.0,
            }
        )

    most_used = None
    if usage:
        key, val = max(usage.items(), key=lambda x: int(x[1]))
        most_used = {"agent": key, "label": key.replace("_", " ").title(), "count": int(val)}

    uploaded_files = memory.get_var("uploaded_files") or []
    if not isinstance(uploaded_files, list):
        uploaded_files = []

    watcher_last = memory.get_var("watcher_auto_trigger_time")
    return {
        "system_performance": {
            "cpu_percent": round(current_cpu, 1),
            "cpu_delta": round(cpu_delta, 1),
            "memory_percent": round(ram.percent, 1),
            "memory_delta": round(ram_delta, 1),
            "disk_percent": round(disk_percent, 1) if disk_percent is not None else None,
            "uptime_display": f"{uptime_hours}h {uptime_mins}m",
            "uptime_delta_seconds": uptime_delta,
            "total_events": total_events,
            "events_delta": events_delta,
        },
        "agent_usage": {
            "items": agent_usage_list,
            "total": total_agent_usage,
            "most_used": most_used,
        },
        "watcher": {
            "enabled": bool(memory.get_var("watcher_enabled")),
            "server_url": memory.get_var("watcher_server_url") or "Not set",
            "watch_dir": memory.get_var("watcher_watch_dir") or "Not set",
            "event_count": _count_events_by_type(events, "watcher"),
            "last_trigger": (
                datetime.fromtimestamp(float(watcher_last)).strftime("%Y-%m-%d %H:%M:%S")
                if watcher_last
                else None
            ),
        },
        "uploaded_files": [
            {
                "name": f.get("name", "Unknown"),
                "path": f.get("path", "N/A"),
                "timestamp": f.get("timestamp", "N/A"),
            }
            for f in uploaded_files
            if isinstance(f, dict)
        ],
        "additional_analytics": {
            "hypothesis_ready": bool(memory.get_var("hypothesis_ready")),
            "has_hypothesis": bool(memory.get_var("last_hypothesis")),
            "has_experimental_outputs": bool(memory.get_var("experimental_outputs")),
            "routing_mode": memory.get_var("routing_mode") or "Autonomous (LLM)",
        },
        "workflow": {
            "active": bool(memory.get_var("workflow_active")),
            "step": memory.get_var("workflow_step") or "N/A",
            "auto_ml_after_curve_fitting": bool(memory.get_var("auto_ml_after_curve_fitting")),
            "analysis_ready": bool(memory.get_var("analysis_ready")),
            "ml_model_choice": memory.get_var("optimization_model_choice") or "Not set",
            "workflow_index": int(memory.get_var("workflow_index") or 0),
        },
        "session_statistics": {
            "total_interactions": len(events),
            "uploaded_files_count": len(uploaded_files),
            "active_sessions": 1,
        },
        "ml_analysis_activity": {
            "curve_fitting_runs": _count_events_by_mode(events, "curve fitting"),
            "ml_models_runs": _count_events_by_mode(events, "ml_models"),
            "analysis_runs": _count_events_by_mode(events, "analysis"),
            "ml_auto_runs": _count_events_by_type(events, "ml_automation"),
        },
        "stage": memory.get_var("stage"),
        "last_hypothesis_preview": (memory.get_var("last_hypothesis") or "")[:500] or None,
    }
