"""
Lightweight MCP client wrapper for the literature agent server.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class MCPToolInfo:
    name: str
    description: str = ""


class MCPClientError(RuntimeError):
    """Base error for MCP client failures."""


class MCPConnectionError(MCPClientError):
    """Raised when MCP endpoint cannot be reached."""


class MCPRequestError(MCPClientError):
    """Raised when MCP request fails after connection."""


def _is_connection_failure(exc: BaseException) -> bool:
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    if "connecterror" in name or "connection attempts failed" in text:
        return True
    nested = getattr(exc, "exceptions", None)
    if nested:
        return any(_is_connection_failure(child) for child in nested)
    return False


class MCPLiteratureClient:
    def __init__(self, endpoint: str, timeout_seconds: float = 60.0):
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds

    async def _call_tool_async(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        try:
            from mcp import ClientSession
            from mcp.client.streamable_http import streamablehttp_client
        except Exception as exc:  # pragma: no cover - import availability depends on runtime
            raise RuntimeError(
                "MCP client dependencies are unavailable. Install with: pip install mcp"
            ) from exc

        try:
            async with streamablehttp_client(self.endpoint) as (read_stream, write_stream, _):
                session = ClientSession(read_stream, write_stream)
                await session.initialize()
                result = await asyncio.wait_for(
                    session.call_tool(tool_name, arguments=arguments or {}),
                    timeout=self.timeout_seconds,
                )
        except Exception as exc:
            if _is_connection_failure(exc):
                raise MCPConnectionError(
                    f"Unable to reach MCP endpoint {self.endpoint}: {type(exc).__name__}: {exc}"
                ) from exc
            raise MCPRequestError(
                f"MCP tool call failed for '{tool_name}' at {self.endpoint}: {type(exc).__name__}: {exc}"
            ) from exc

        # Convert MCP result to a JSON-serializable shape.
        payload = {
            "ok": True,
            "tool": tool_name,
            "raw_result": None,
            "content": [],
        }
        payload["raw_result"] = getattr(result, "model_dump", lambda: str(result))()
        content = getattr(result, "content", None)
        if content:
            serialized: List[Dict[str, Any]] = []
            for item in content:
                if hasattr(item, "model_dump"):
                    serialized.append(item.model_dump())
                else:
                    serialized.append({"text": str(item)})
            payload["content"] = serialized
        return payload

    async def _list_tools_async(self) -> List[MCPToolInfo]:
        try:
            from mcp import ClientSession
            from mcp.client.streamable_http import streamablehttp_client
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "MCP client dependencies are unavailable. Install with: pip install mcp"
            ) from exc

        try:
            async with streamablehttp_client(self.endpoint) as (read_stream, write_stream, _):
                session = ClientSession(read_stream, write_stream)
                await session.initialize()
                result = await asyncio.wait_for(
                    session.list_tools(),
                    timeout=self.timeout_seconds,
                )
                tools = getattr(result, "tools", []) or []
                return [
                    MCPToolInfo(
                        name=getattr(tool, "name", ""),
                        description=getattr(tool, "description", "") or "",
                    )
                    for tool in tools
                    if getattr(tool, "name", "")
                ]
        except Exception as exc:
            if _is_connection_failure(exc):
                raise MCPConnectionError(
                    f"Unable to reach MCP endpoint {self.endpoint}: {type(exc).__name__}: {exc}"
                ) from exc
            raise MCPRequestError(
                f"MCP tool discovery failed at {self.endpoint}: {type(exc).__name__}: {exc}"
            ) from exc

    def call_tool(self, tool_name: str, arguments: Dict[str, Any] | None = None) -> Dict[str, Any]:
        return asyncio.run(self._call_tool_async(tool_name, arguments or {}))

    def list_tools(self) -> List[MCPToolInfo]:
        return asyncio.run(self._list_tools_async())
