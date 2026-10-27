"""Calls the tax tools over MCP: starts `python -m src.tax_math_mcp` as a child process (stdio)
and keeps one session open for the life of the process.

Why a thread: graph nodes are synchronous, MCP is async. The session lives on its own event loop
in a daemon thread and `call` hands work to it, so any number of graph threads can use it.

Why no silent fallback: if the server cannot start, `McpUnavailable` says so and the run stops.
Quietly computing in-process instead would hide that the "deterministic MCP tool call" rule is
not being met. Set SILVERFILE_TOOL_TRANSPORT=local to use the in-process functions on purpose
(tests, debugging); each trace record says which transport its tools used.
"""
import asyncio
import atexit
import os
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRANSPORT_ENV = "SILVERFILE_TOOL_TRANSPORT"
STARTUP_TIMEOUT = 60  # seconds; the first start imports the tax tools
CALL_TIMEOUT = 30


class McpUnavailable(RuntimeError):
    """The tax-tool server could not be started or reached."""


def tool_transport() -> str:
    """"mcp" (the default) or "local"."""
    value = os.environ.get(TRANSPORT_ENV, "mcp").strip().lower()
    if value not in ("mcp", "local"):
        raise ValueError(f"{TRANSPORT_ENV} must be 'mcp' or 'local', not {value!r}")
    return value


class McpToolClient:
    transport = "mcp"

    def __init__(self, module: str = "src.tax_math_mcp", cwd: Path = ROOT):
        self._module, self._cwd = module, Path(cwd)
        self._lock = threading.Lock()
        self._thread = None
        self._loop = None
        self._session = None
        self._stop = None
        self._ready = threading.Event()
        self._error: BaseException | None = None

    # ---- lifecycle -------------------------------------------------------------------

    def start(self) -> None:
        with self._lock:
            if self._session is not None:
                return
            self._ready.clear()
            self._error = None
            self._thread = threading.Thread(target=self._run, name="mcp-tax-tools", daemon=True)
            self._thread.start()
            if not self._ready.wait(STARTUP_TIMEOUT):
                raise McpUnavailable(f"the tax tool server did not start within {STARTUP_TIMEOUT} seconds")
            if self._error is not None:
                raise McpUnavailable(f"the tax tool server could not start: {self._error}") from self._error

    def _run(self) -> None:
        try:
            asyncio.run(self._serve())
        except BaseException as exc:  # reported to whoever is waiting in start()
            self._error = self._error or exc
        finally:
            self._session = None
            self._ready.set()

    async def _serve(self) -> None:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        self._loop = asyncio.get_running_loop()
        self._stop = asyncio.Event()
        params = StdioServerParameters(command=sys.executable, args=["-m", self._module], cwd=str(self._cwd))
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                self._session = session
                self._ready.set()
                await self._stop.wait()

    def close(self) -> None:
        loop, stop, thread = self._loop, self._stop, self._thread
        if loop is not None and stop is not None and thread is not None and thread.is_alive():
            loop.call_soon_threadsafe(stop.set)
            thread.join(timeout=10)
        self._session = None

    # ---- calls -----------------------------------------------------------------------

    def call(self, name: str, **arguments) -> dict:
        """Run a tool and return its provenance record. A tool error (bad input) raises
        ValueError, as the in-process function would; an unreachable server raises McpUnavailable."""
        self.start()
        try:
            future = asyncio.run_coroutine_threadsafe(self._session.call_tool(name, arguments), self._loop)
            result = future.result(CALL_TIMEOUT)
        except McpUnavailable:
            raise
        except Exception as exc:
            raise McpUnavailable(f"the tax tool server failed while running {name}: {exc}") from exc
        if result.is_error:
            text = " ".join(getattr(c, "text", "") for c in result.content).strip()
            raise ValueError(f"{name}: {text}")
        record = result.structured_content
        if not isinstance(record, dict):
            raise McpUnavailable(f"{name} returned no structured result")
        return record

    def tool(self, name: str):
        def call_over_mcp(**arguments):
            return self.call(name, **arguments)

        call_over_mcp.__name__ = name
        call_over_mcp.transport = "mcp"
        return call_over_mcp


_shared: McpToolClient | None = None
_shared_lock = threading.Lock()


def shared_client() -> McpToolClient:
    """One client for the whole process, started on first use."""
    global _shared
    with _shared_lock:
        if _shared is None:
            _shared = McpToolClient()
            atexit.register(_shared.close)
        return _shared


def mcp_registry() -> dict:
    """name -> callable for every tax tool, each of which calls the MCP server."""
    from src.tax_tools import TAX_TOOLS

    client = shared_client()
    return {name: client.tool(name) for name in TAX_TOOLS}
