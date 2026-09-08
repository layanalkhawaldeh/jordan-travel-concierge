import asyncio
import json
import sys
from mcp.server import Server
from mcp.server.stdio import stdio_server
import mcp.types as types

# Initialize the MCP Server (Model Context Protocol)
server = Server("jordan-tourism-mcp-server")

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """Exposes tourism tools through the standardized Model Context Protocol."""
    return [
        types.Tool(
            name="search_hotels",
            description="Search available hotels in a specific city with optional stars and budget limits.",
            inputSchema={
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "City in Jordan (Amman, Petra, Dead Sea, Wadi Rum, Aqaba)"},
                    "stars": {"type": "integer", "description": "Star rating (2-5)"},
                    "max_price": {"type": "number", "description": "Max budget per night in USD"}
                },
                "required": ["city"]
            }
        ),
        types.Tool(
            name="search_places",
            description="Search interesting places, attractions, landmarks, and restaurants in Jordan.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Attraction name or keyword (e.g. Petra, Jerash, Roman Theater)"}
                },
                "required": ["query"]
            }
        ),
        types.Tool(
            name="create_booking",
            description="Directly creates a travel booking reservation in pending_payment state.",
            inputSchema={
                "type": "object",
                "properties": {
                    "conversation_id": {"type": "string", "description": "The active conversation ID"}
                },
                "required": ["conversation_id"]
            }
        )
    ]

@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """Executes a tool call requested by the MCP client."""
    try:
        if name == "search_hotels":
            from src.tools.search import search_hotels
            city = arguments.get("city")
            stars = arguments.get("stars")
            max_price = arguments.get("max_price")
            result = search_hotels(city, stars, max_price)
            return [types.TextContent(type="text", text=result)]

        elif name == "search_places":
            from src.tools.search import search_places
            query = arguments.get("query")
            result = search_places(query)
            return [types.TextContent(type="text", text=result)]

        elif name == "create_booking":
            from src.tools.operations import create_booking
            conversation_id = arguments.get("conversation_id")
            result = create_booking(conversation_id)
            return [types.TextContent(type="text", text=result)]

        else:
            raise ValueError(f"Unknown MCP tool: {name}")

    except Exception as e:
        return [types.TextContent(type="text", text=json.dumps({"success": False, "error": str(e)}))]

async def main():
    # Run the server using Stdio transport (stdin/stdout)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )

if __name__ == "__main__":
    # Standard entry point to launch the stdio server
    asyncio.run(main())
