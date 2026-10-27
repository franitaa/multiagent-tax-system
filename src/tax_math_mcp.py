"""The deterministic tax tools as an MCP server (Assignment 7: "every number comes from a
deterministic MCP tool call"). The tools are the same functions the Computation agent calls
in-process through its ToolBox (src/orchestration/access.py::TOOLS); this exposes them over MCP.

Run (stdio):  python -m src.tax_math_mcp      Requires: pip install "mcp>=2"
"""
from mcp.server.mcpserver import MCPServer

from src.orchestration.access import TOOLS

server = MCPServer("silverfile-tax-math")
for _name, _fn in TOOLS.items():
    server.add_tool(_fn, name=_name, description=(_fn.__doc__ or _name).strip().splitlines()[0])

if __name__ == "__main__":
    server.run()
