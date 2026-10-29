"""The deterministic tax tools as an MCP server (Assignment 7: "every number comes from a
deterministic MCP tool call"). Computation and Review call these through src/mcp_client.py,
which starts this server over stdio.

Run by hand (stdio):  python -m src.tax_math_mcp      Requires: pip install "mcp>=2"
Only the tax tools are served (src/tax_tools.py); nothing here reads state or documents.
"""
from mcp.server.mcpserver import MCPServer

from src.tax_tools import TAX_TOOLS

server = MCPServer("silverfile-tax-math")
for _name, _fn in TAX_TOOLS.items():
    server.add_tool(_fn, name=_name, description=(_fn.__doc__ or _name).strip().splitlines()[0])

if __name__ == "__main__":
    server.run()
