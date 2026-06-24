import pytest
import os


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/test.db")
    import importlib
    import app.db.engine as eng
    importlib.reload(eng)
    eng._engine = None  # reset singleton
    import app.tools.database as dbmod
    importlib.reload(dbmod)
    manager = dbmod.DatabaseManager()
    manager.init_schema()
    manager.ensure_defaults()
    return manager


def test_get_returns_default_for_unknown_key(db):
    assert db.get("nonexistent_key", "fallback") == "fallback"


def test_set_and_get_app_config_string(db):
    db.set("api_key", "test-key-123")
    assert db.get("api_key") == "test-key-123"


def test_set_and_get_app_config_bool(db):
    db.set("experimental_mode", True)
    assert db.get("experimental_mode") is True


def test_set_and_get_app_config_int(db):
    db.set("current_experiment_id", 42)
    assert db.get("current_experiment_id") == 42


def test_set_and_get_json(db):
    db.set("experimental_constraints", {"techniques": ["NMR"], "equipment": [], "parameters": [], "focus_areas": [], "liquid_handling": {}})
    result = db.get("experimental_constraints")
    assert result["techniques"] == ["NMR"]


def test_append_and_get_conversation_events(db):
    db.append_conversation_event("test_event", "graph", "session-1", {"key": "val"})
    events = db.get_conversation_events()
    assert len(events) == 1
    assert events[0]["type"] == "test_event"
    assert events[0]["payload"]["key"] == "val"


def test_create_and_get_user(db):
    db.create_user("user-1", "Alice")
    user = db.get_user("user-1")
    assert user["name"] == "Alice"


def test_create_experiment_and_list(db):
    db.create_user("user-1", "Alice")
    exp_id = db.create_experiment("user-1", "My Experiment")
    experiments = db.list_experiments("user-1")
    assert len(experiments) == 1
    assert experiments[0]["name"] == "My Experiment"
    assert experiments[0]["id"] == exp_id


def test_save_and_get_workflow(db):
    db.save_workflow("wf1", [{"name": "Hypothesis Agent", "automatic": False}])
    wfs = db.get_workflows()
    assert "wf1" in wfs
    assert wfs["wf1"]["steps"][0]["name"] == "Hypothesis Agent"


def test_add_and_get_uploaded_file(db):
    db.add_uploaded_file("data.csv", "/tmp/data.csv")
    files = db.get_uploaded_files()
    assert len(files) == 1
    assert files[0]["name"] == "data.csv"


def test_add_and_get_negative_hypothesis(db):
    db.add_negative_hypothesis("H1", "rejected", research_question="Q?", analysis_summary="summary")
    results = db.get_negative_hypotheses()
    assert len(results) == 1
    assert results[0]["hypothesis_text"] == "H1"


def test_add_and_get_hypothesis_outcome(db):
    db.add_hypothesis_outcome("H2", "confirmed", material_hint="NMR", evidence_summary="strong")
    results = db.get_hypothesis_outcomes()
    assert len(results) == 1
    assert results[0]["status"] == "confirmed"


def test_experiment_scoped_set_get(db):
    db.create_user("user-1", "Alice")
    exp_id = db.create_experiment("user-1", "Exp")
    db.set("current_experiment_id", exp_id)
    db.set("research_goal", "test goal")
    assert db.get("research_goal") == "test goal"


def test_clear_session_state(db):
    db.set("stage", "hypothesis")
    db.clear_session_state()
    # After clear, should return default or None
    result = db.get("stage")
    assert result is None or result == "initial"
