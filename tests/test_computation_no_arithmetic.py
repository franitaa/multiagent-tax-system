"""Assignment 7: Computation must not do arithmetic itself; every number comes from a tool call.
Fails if src/agents/computation.py applies an arithmetic operator or min/max/sum/round/abs."""
import ast
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "src" / "agents" / "computation.py"
ARITHMETIC_CALLS = {"sum", "min", "max", "round", "abs", "pow", "divmod"}


def _is_text_or_list_join(node):
    """`a + b` that builds a string or list (a str literal, f-string or list literal inside it)."""
    return node.op.__class__ is ast.Add and any(
        isinstance(n, (ast.JoinedStr, ast.List)) or (isinstance(n, ast.Constant) and isinstance(n.value, str))
        for n in ast.walk(node))


def _arithmetic():
    found = []
    for node in ast.walk(ast.parse(SOURCE.read_text(encoding="utf-8"))):
        if isinstance(node, ast.BinOp) and _is_text_or_list_join(node):
            continue
        if isinstance(node, (ast.BinOp, ast.AugAssign)):
            found.append((node.lineno, type(node.op).__name__))
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            found.append((node.lineno, "unary " + type(node.op).__name__))
        elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
              and node.func.id in ARITHMETIC_CALLS):
            found.append((node.lineno, node.func.id + "()"))
    return found


def test_computation_agent_contains_no_arithmetic():
    assert _arithmetic() == []
