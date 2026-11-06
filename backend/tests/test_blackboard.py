import pytest

from app.orchestrator.blackboard import Blackboard


def test_write_then_read():
    bb = Blackboard()  # memory-only
    bb.write("u1", "resume", {"skills": ["python"]}, agent="resume_agent")
    state = bb.read("u1")
    assert state["resume"] == {"skills": ["python"]}
    assert state["_meta"]["resume"]["updated_by"] == "resume_agent"


def test_sections_are_independent():
    bb = Blackboard()
    bb.write("u1", "resume", {"skills": ["python"]}, agent="a")
    bb.write("u1", "career", {"target": "Data Analyst"}, agent="b")
    state = bb.read("u1")
    assert state["resume"]["skills"] == ["python"]
    assert state["career"]["target"] == "Data Analyst"
    assert state["_version"] == 2


def test_unknown_section_rejected():
    with pytest.raises(ValueError):
        Blackboard().write("u1", "hacker", {}, agent="x")


def test_read_returns_copy():
    bb = Blackboard()
    bb.write("u1", "resume", {"skills": ["python"]}, agent="a")
    bb.read("u1")["resume"]["skills"].append("oops")
    assert bb.read("u1")["resume"]["skills"] == ["python"]
