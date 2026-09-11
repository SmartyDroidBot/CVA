"""Tests for PentestEngine — planner/executor loop, driven by a stub LLM.

No real model or tools: a FakeLLM scripts planner + executor turns and a FakeTool
records calls, so the loop's control flow is verified deterministically.
"""

import pytest
from langchain_core.messages import ToolMessage

from src.engine import PentestEngine, parse_task_list
from src.tracker.task_tree import TaskTree, Phase


# ── Stubs ─────────────────────────────────────────────────────────────────────

class FakeAI:
    """Minimal stand-in for an AIMessage (duck-typed on content/tool_calls)."""
    def __init__(self, content="", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []


class FakeTool:
    def __init__(self, name="execute_shell_command"):
        self.name = name
        self.calls = []

    def invoke(self, args):
        self.calls.append(args)
        return f"[output of {self.name} {args}]"


class FakeLLM:
    """Scripts planner and executor turns.

    - Planner call (system prompt contains 'PLANNER') → returns ``plan_json``.
    - Executor call → one tool call the first time, then a final summary once a
      ToolMessage is present in the conversation.
    """
    def __init__(self, plan_json: str):
        self.plan_json = plan_json

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        system = messages[0].content if messages else ""
        if "PLANNER" in system:
            return FakeAI(content=self.plan_json)
        # Executor: if a tool already ran in this task, finish; else call one.
        if any(isinstance(m, ToolMessage) for m in messages):
            return FakeAI(content="Task complete: summary of findings.")
        return FakeAI(content="Running a scan.", tool_calls=[
            {"name": "execute_shell_command", "args": {"command": "nmap -sV t"}, "id": "c1"},
        ])


PLAN_JSON = """[
  {"description": "Scan ports on the target", "phase": "reconnaissance"},
  {"description": "Test web inputs for SQL injection", "phase": "vulnerability_analysis"}
]"""


# ── parse_task_list ───────────────────────────────────────────────────────────

def test_parse_task_list_valid():
    tasks = parse_task_list(PLAN_JSON)
    assert len(tasks) == 2
    assert tasks[0]["description"] == "Scan ports on the target"
    assert tasks[1]["phase"] == "vulnerability_analysis"


def test_parse_task_list_with_prose_and_fence():
    text = 'Here is the plan:\n```json\n[{"description":"do a thing"}]\n```\nThanks!'
    tasks = parse_task_list(text)
    assert tasks == [{"description": "do a thing", "phase": "reconnaissance"}]


def test_parse_task_list_garbage():
    assert parse_task_list("no json here") == []
    assert parse_task_list("") == []
    assert parse_task_list("{not a list}") == []


# ── Engine ────────────────────────────────────────────────────────────────────

@pytest.fixture
def engine():
    tool = FakeTool()
    eng = PentestEngine(llm=FakeLLM(PLAN_JSON), tools=[tool], target="http://t")
    eng._tool = tool  # expose for assertions
    return eng


def test_plan_populates_graph(engine):
    tasks = engine.plan("pentest http://t")
    assert len(tasks) == 2
    assert engine.graph.get_task("t1").phase == Phase.RECON
    assert engine.graph.get_task("t2").phase == Phase.VULN


def test_plan_falls_back_to_default(monkeypatch):
    eng = PentestEngine(llm=FakeLLM("not json at all"), tools=[FakeTool()], target="t")
    tasks = eng.plan("goal")
    assert len(tasks) == 5   # default 5-phase plan
    assert tasks[0].phase == Phase.RECON


def test_run_task_invokes_tool(engine):
    engine.plan("goal")
    task = engine.graph.get_task("t1")
    out = engine.run_task(task)
    assert engine._tool.calls == [{"command": "nmap -sV t"}]
    assert "summary" in out.lower()
    # The tool run was logged as an action, with recon phase inferred from nmap.
    assert engine.graph.nodes and engine.graph.nodes[-1].phase == Phase.RECON


def test_run_completes_all_tasks(engine):
    events = []
    engine.on_event = lambda kind, data: events.append(kind)
    graph = engine.run("pentest http://t")
    assert graph.tasks_complete()
    assert all(t.status == "done" for t in graph.all_tasks())
    assert "planned" in events and "finished" in events
    # Two tasks, each invoking the tool once.
    assert len(engine._tool.calls) == 2


def test_run_respects_max_tasks():
    eng = PentestEngine(llm=FakeLLM(PLAN_JSON), tools=[FakeTool()],
                        target="t", max_tasks=1)
    graph = eng.run("goal")
    done = [t for t in graph.all_tasks() if t.status == "done"]
    assert len(done) == 1   # stopped after the cap


# ── Interactive (answer) + orchestrator-compatible surface ────────────────────

def test_answer_runs_a_turn_and_calls_tool(engine):
    produced = engine.answer("scan the target")
    assert engine._tool.calls == [{"command": "nmap -sV t"}]
    # History holds the human turn plus the produced messages.
    assert engine.history[0].content == "scan the target"
    assert len(produced) >= 2


def test_answer_accumulates_history(engine):
    engine.answer("first request")
    n1 = len(engine.history)
    engine.answer("second request")
    assert len(engine.history) > n1
    assert any(getattr(m, "content", "") == "second request" for m in engine.history)


def test_invoke_wraps_answer(engine):
    out = engine.invoke("do a scan")
    assert "messages" in out and out["messages"]


def test_set_target_and_active_agent(engine):
    engine.set_target("http://x/")
    assert engine.target == "http://x"          # trailing slash trimmed
    assert engine.graph.target == "http://x"
    assert isinstance(engine.active_agent, str)


def test_get_and_update_messages(engine):
    engine.answer("x")
    assert engine.get_messages()
    engine.update_messages([])
    assert engine.get_messages() == []


def test_inject_message_appends(engine):
    from langchain_core.messages import HumanMessage
    engine.inject_message(HumanMessage(content="/run output here"))
    assert engine.history[-1].content == "/run output here"
