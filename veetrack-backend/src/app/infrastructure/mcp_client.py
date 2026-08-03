"""MCP Client for ApiDirect JSON-RPC Server.

This module provides a simple async client to interact with the ApiDirect MCP
server, which exposes tools like Twitter, YouTube, and Web Search for the agent.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

class ApiDirectMCPClient:
    """Client for ApiDirect's JSON-RPC MCP Server."""

    def __init__(self, api_key: str, base_url: str = "https://apidirect.io/mcp"):
        self.api_key = api_key
        self.url = f"{base_url}?token={api_key}"

    async def call_tool(self, method: str, params: dict[str, Any] | None = None) -> str:
        """Execute an MCP tool via JSON-RPC."""
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "id": 1,
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.url,
                    json=payload,
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()
                
                if "error" in data:
                    logger.warning(
                        "mcp_client.tool_error",
                        method=method,
                        error=data["error"],
                    )
                    return f"Error from tool {method}: {data['error']}"
                
                return json.dumps(data.get("result", {}))
                
        except Exception as exc:
            logger.error(
                "mcp_client.request_failed",
                method=method,
                error=str(exc),
            )
            return f"Failed to execute {method}: {exc}"
