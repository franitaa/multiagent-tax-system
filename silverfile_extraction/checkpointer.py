"""MEM-1: shared synchronous checkpointer factory for P1/P2's parent graph."""
from contextlib import contextmanager
from pathlib import Path
import re

from .privacy import SafeInputError


def case_config(case_id: str) -> dict:
    """The chat page's case ID IS the LangGraph thread ID; it is not authentication."""
    if not isinstance(case_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", case_id):
        raise SafeInputError("Case ID must contain 1-64 letters, digits, underscores or hyphens.")
    return {"configurable": {"thread_id": case_id}}


@contextmanager
def sqlite_checkpointer(db_path: str | Path = "runtime/team_checkpoints.sqlite"):
    """Keep this context open for the graph's lifetime; use one parent checkpointer.

    This synchronous factory does not replace P4's state schema. The graph builder
    supplied by P1 can have any compatible state, including messages and intake data.
    """
    from langgraph.checkpoint.sqlite import SqliteSaver
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with SqliteSaver.from_conn_string(str(path)) as saver:
        yield saver

