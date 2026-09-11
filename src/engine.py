"""PentestEngine — the shared planner/executor loop.

This is the single execution engine both autonomous and (later) interactive
modes drive, replacing the two divergent agent paths. Shape (VulnBot /
HackingBuddyGPT style):

    plan(goal)  → fills the task graph
    run()       → while ready tasks remain: mark running → run_task → mark done

``run_task`` is a bounded ReAct loop (LLM ↔ tools) with focused context: the
task, the current graph state, and knowledge-base hits. A deterministic harness
wraps the model — defensive plan parsing, a default plan fallback, bounded
iterations, tool-output trimming — so weak local models degrade instead of
looping forever.

Display/telemetry is delivered through an ``on_event(kind, data)`` callback so
callers (e.g. auto mode's Rich UI) render without the engine importing any UI.
"""

import json
import re
from typing import Callable, Dict, List, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from src.brain.thinking import strip_thinking
from src.guardrails.injection import screen_tool_output
from src.tracker.task_tree import Phase, TaskTree, infer_phase_from_command

MAX_TASK_ROUNDS = 6      # LLM↔tool iterations per task
MAX_TASKS = 20           # safety cap on total tasks executed
TOOL_OUTPUT_CAP = 3000   # chars of tool output fed back to the model


def _phase_from_str(value: str) -> Phase:
    try:
        return Phase(value)
    except Exception:
        try:
            return Phase[value.upper()]
        except Exception:
            return Phase.RECON


def parse_task_list(text: str) -> List[Dict]:
    """Extract a task list from planner output, defensively.

    Accepts a JSON array of objects with at least ``description`` (and optional
    ``phase``). Returns [] when nothing parseable is found.
    """
    if not text:
        return []
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return []
    try:
        raw = json.loads(text[start:end + 1])
    except Exception:
        return []
    tasks = []
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, dict) and item.get("description"):
            tasks.append({
                "description": str(item["description"]).strip(),
                "phase": str(item.get("phase", "reconnaissance")),
            })
        elif isinstance(item, str) and item.strip():
            tasks.append({"description": item.strip(), "phase": "reconnaissance"})
    return tasks


_PLANNER_SYSTEM = """\
You are the PLANNER for an authorized penetration test of {target}.
Break the engagement into a short ordered list of concrete tasks across the VAPT
phases (reconnaissance, enumeration, vulnerability_analysis, exploitation,
post_exploitation, reporting).

Reply with ONLY a JSON array, no prose. Each element:
  {{"description": "<one concrete task>", "phase": "<phase>"}}
Keep it to 4-8 tasks. Order them so earlier tasks inform later ones."""

_EXECUTOR_SYSTEM = """\
You are CVA, an autonomous penetration tester working an AUTHORIZED engagement
against {target}. You are currently in the {phase} phase.

Execute this task by running tools yourself — pass concrete commands to
execute_shell_command (nmap, gobuster, sqlmap, curl, ...). Do NOT ask permission
and do NOT just suggest commands. Analyse each result briefly, then act. When the
task is complete, summarise what you found in 1-3 lines.

{graph_ctx}{kb_ctx}"""


class PentestEngine:
    """Plans an engagement into a task graph and executes each task via ReAct."""

    def __init__(self, llm, tools: List, target: str = "", kb=None,
                 task_graph: Optional[TaskTree] = None, session_logger=None,
                 on_event: Optional[Callable[[str, dict], None]] = None,
                 max_task_rounds: int = MAX_TASK_ROUNDS, max_tasks: int = MAX_TASKS):
        self.llm = llm
        self.tools = tools or []
        self.tool_map = {t.name: t for t in self.tools}
        self.target = target
        self.kb = kb
        self.graph = task_graph or TaskTree(target=target)
        if target and not self.graph.target:
            self.graph.target = target
        self.session_logger = session_logger
        self.on_event = on_event or (lambda kind, data: None)
        self.max_task_rounds = max_task_rounds
        self.max_tasks = max_tasks
        self._llm_tools = llm.bind_tools(self.tools) if self.tools else llm

    def _emit(self, kind: str, **data):
        try:
            self.on_event(kind, data)
        except Exception:
            pass

    # ── Planning ──────────────────────────────────────────────────────────────

    def plan(self, goal: str) -> List:
        """Populate the task graph from the goal. Falls back to a default plan."""
        system = _PLANNER_SYSTEM.format(target=self.target or "the target")
        try:
            resp = self.llm.invoke([SystemMessage(content=system),
                                    HumanMessage(content=goal)])
            text = strip_thinking(getattr(resp, "content", "") or "")
        except Exception as e:
            self._emit("plan_error", error=str(e))
            text = ""

        for item in parse_task_list(text):
            self.graph.add_task(item["description"], phase=_phase_from_str(item["phase"]))

        if not self.graph.tasks:
            self._default_plan(goal)

        tasks = self.graph.all_tasks()
        self._emit("planned", tasks=tasks)
        return tasks

    def _default_plan(self, goal: str):
        """Deterministic fallback when the planner produces nothing usable."""
        defaults = [
            ("Reconnaissance: fingerprint services and gather information", Phase.RECON),
            ("Enumeration: discover content, directories, and services", Phase.ENUM),
            ("Vulnerability analysis: probe discovered inputs for common flaws", Phase.VULN),
            ("Exploitation: validate and exploit confirmed vulnerabilities", Phase.EXPLOIT),
            ("Post-exploitation: assess impact of any access gained", Phase.POST_EXPLOIT),
        ]
        for desc, phase in defaults:
            self.graph.add_task(desc, phase=phase)

    # ── Execution ───────────────────────────────────────────────────────────────

    def run_task(self, task) -> str:
        """Run a bounded ReAct loop for one task; return the model's final text."""
        kb_ctx = ""
        if self.kb is not None:
            try:
                hits = self.kb.get_context(task.phase.value, task.description)
                if hits:
                    kb_ctx = f"\n\n## RELEVANT KNOWLEDGE\n{hits[:2000]}"
            except Exception:
                kb_ctx = ""
        graph_ctx = self.graph.get_context_for_agent()
        graph_ctx = f"{graph_ctx}\n\n" if graph_ctx else ""

        system = _EXECUTOR_SYSTEM.format(
            target=self.target or "the target",
            phase=task.phase.value.replace("_", " "),
            graph_ctx=graph_ctx, kb_ctx=kb_ctx,
        )
        convo = [SystemMessage(content=system), HumanMessage(content=task.description)]
        produced: List[str] = []

        for _ in range(self.max_task_rounds):
            result = self._llm_tools.invoke(convo)
            convo.append(result)

            content = getattr(result, "content", "")
            if isinstance(content, str) and content.strip():
                clean = strip_thinking(content).strip()
                if clean:
                    produced.append(clean)
                    self._emit("assistant", text=clean)

            tool_calls = getattr(result, "tool_calls", None)
            if not tool_calls:
                break

            for tc in tool_calls:
                name, args = tc.get("name", ""), tc.get("args", {}) or {}
                self._emit("tool_call", name=name, args=args)
                tool = self.tool_map.get(name)
                if tool is None:
                    output = f"Unknown tool: {name}"
                else:
                    try:
                        output = str(tool.invoke(args))
                    except Exception as e:
                        output = f"Tool error: {e}"
                self._emit("tool_result", name=name, output=output)
                if self.session_logger:
                    try:
                        self.session_logger.log_tool_result(name, output)
                    except Exception:
                        pass
                command = args.get("command", "") if isinstance(args, dict) else ""
                self.graph.add_action(f"Task {task.id}: {name}", tool=name,
                                      result_summary=output[:100], command=command)
                # Fence attacker-influenced output as untrusted data before it
                # re-enters the model (indirect prompt-injection defense).
                screened = screen_tool_output(output[:TOOL_OUTPUT_CAP])
                convo.append(ToolMessage(content=screened,
                                         tool_call_id=tc.get("id", name), name=name))

        return "\n".join(produced)

    def run(self, goal: str) -> TaskTree:
        """Plan then execute tasks until the graph is drained or the cap is hit."""
        self.plan(goal)
        executed = 0
        while executed < self.max_tasks:
            ready = self.graph.ready_tasks()
            if not ready:
                break
            task = ready[0]
            self.graph.mark(task.id, "running")
            self._emit("task_start", task=task)
            try:
                result = self.run_task(task)
                self.graph.mark(task.id, "done", result=result[:500])
            except Exception as e:
                self.graph.mark(task.id, "failed", result=str(e))
                self._emit("task_error", task=task, error=str(e))
            self._emit("task_done", task=task)
            executed += 1
        self._emit("finished", executed=executed)
        return self.graph
