# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp>=2"]
# ///
"""Rook's render tool over MCP: Rook's agent shows a diagram in the swarm, lights its nodes, or clears it. Each call goes
to the running Rook over its socket, and Rook passes it to the overlay."""

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import relay  # noqa: E402

from mcp.server.mcpserver import MCPServer  # noqa: E402
from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402

# The old scene tools are gone. An agent with a stale tool list, or an old session, gets this refusal, not a crash.
GONE = {"show_scene", "show_step"}
GONE_SAID = ("show_scene and show_step are gone. Call show_diagram with a graph such as \"browser > dns > server\", or "
             "start your answer with the {diagram} mark.")


class RenderServer(MCPServer):
    async def call_tool(self, name, arguments, context=None):
        if name in GONE:
            raise ToolError(GONE_SAID)
        return await super().call_tool(name, arguments, context)


mcp = RenderServer("render")


def call(request):
    """Rook's answer to a render request, with the owner's name filled in."""
    return relay.settings.render(_call(request))


def _call(request):
    answer = relay.ask_rook("render", json.dumps(request), wait=15)
    if answer is None:
        return "Rook is not running, so nothing can show."
    if answer.get("ok"):
        return answer.get("said") or "Done."
    return answer.get("error") or "The diagram did not show."


@mcp.tool(structured_output=False)
def show_diagram(graph: str, title: str = "", shapes: dict[str, str] | None = None) -> str:
    """Show a diagram of how things connect, when you cannot start your answer with the {diagram} mark: outside
    speech, or after a tool call. graph is the mark's graph, such as "browser > dns:globe > server* > page:file". Its
    nodes light as your voice names them. shapes, as the mark's third section, draws a node that no icon fits:
    {node name: SVG path}, such as {"rocket": "M0-10C4-6 4 2 3 6H-3C-4 2-4-6 0-10ZM-4 1-7 7H-3M4 1 7 7H3"}, on
    viewBox -12 -12 24 24, centred on 0, y down. Draw one clear outline in a few strokes, with no fills or text, details
    2 units apart and points within 10.5 of the centre."""
    return call({"diagram": {"graph": graph, "title": title, **({"shapes": shapes} if shapes else {})}})


@mcp.tool(structured_output=False)
def clear_scene() -> str:
    """Clear the scene on screen now. Call it only when the scene no longer fits what you are saying; scenes also
    clear by themselves."""
    return call({"clear": True})


if __name__ == "__main__":
    mcp.run()
