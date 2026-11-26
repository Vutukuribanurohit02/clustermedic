"""Start the MCP server over stdio, list its tools, call two of them. Usage: python scripts/mcp_smoke.py"""
import asyncio
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    params = StdioServerParameters(command=sys.executable, args=["-m", "clustermedic.mcp_server"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()
            tools = (await s.list_tools()).tools
            print(f"{len(tools)} tools:", ", ".join(t.name for t in tools))
            for name, args in [("cluster_anomalies", {}), ("search_runbooks", {"query": "node shows idle*", "k": 2})]:
                res = await s.call_tool(name, args)
                text = res.content[0].text if res.content else str(res)
                print(f"\n{name} -> {text[:400]}")

asyncio.run(main())
