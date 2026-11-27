# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp>=2"]
# ///
"""Rook's render tool over MCP: Rook's Claude draws a scene with the swarm, in one reply. Each call goes to the running
Rook over its socket, and Rook passes it to the overlay, which checks the scene again before it draws anything."""

import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import relay  # noqa: E402
import render  # noqa: E402

from mcp.server.mcpserver import MCPServer  # noqa: E402

OWNER = relay.settings.OWNER_TOKEN  # The owner's name, filled in when the text leaves Rook.


def pn(phrase, they=None):
    """The owner token for a phrase written with he, such as \"his\" or \"he asks\". A phrase with a verb
    gives its they form too."""
    return relay.settings.token(phrase, they)



mcp = MCPServer("render")
WHEN = render.TOOL_GUIDE
# Antigravity declares only so many bytes of tools in a session. With T3's tools, show_scene, Rook's largest, was
# left out (2026-11-23). Under Antigravity the harness sets ROOK_RENDER_BRIEF and puts the guide in Neon's system prompt.
BRIEF = os.environ.get("ROOK_RENDER_BRIEF") == "1"
BRIEF_WHEN = (f"Show {OWNER} a scene: your swarm of gold dust forms a drawing on {pn('his')} screen while you answer. How to write "
              "scenes and time their steps is in your instructions, under \"Render scenes\".")


def call(request):
    """Rook's answer to a render request, with the owner's name filled in."""
    return relay.settings.render(_call(request))


def _call(request):
    answer = relay.ask_rook("render", json.dumps(request), wait=15)
    if answer is None:
        return "Rook is not running, so nothing can show."
    if answer.get("ok"):
        return answer.get("said") or "Done."
    return "\n".join(answer.get("errors") or [answer.get("error") or "The scene did not show."])


@mcp.tool(structured_output=False, description=relay.settings.render(BRIEF_WHEN if BRIEF else WHEN + render.describe()))
def show_scene(scene: dict | str) -> str:
    if isinstance(scene, str):
        try:
            scene = json.loads(scene)
        except ValueError as error:
            return f"The scene is not valid JSON: {error}."
    # The overlay's answer still names show_step for each step; marks in the answer are the way now.
    return call({"scene": scene}).replace("call show_step to light each", "mark each in your answer with {step N}")


@mcp.tool(structured_output=False)
def show_diagram(graph: str, title: str = "") -> str:
    """Show a diagram of how things connect, when you cannot start your answer with the {diagram} mark: outside
    speech, or after a tool call. graph is the mark's graph, such as "browser > dns:globe > server* > page:file". Its
    nodes light as your voice names them."""
    return call({"diagram": {"graph": graph, "title": title}})


@mcp.tool(structured_output=False)
def show_step(step: int) -> str:
    """Light one step of the scene on screen now: 1 for its first step. 0 shows the whole scene again, with no step
    lit. Use it only for a step outside your spoken answer; in speech, {step N} marks time each step to your voice."""
    return call({"step": step})


@mcp.tool(structured_output=False)
def clear_scene() -> str:
    """Clear the scene on screen now. Call it only when the scene no longer fits what you are saying; scenes also
    clear by themselves."""
    return call({"clear": True})


if __name__ == "__main__":
    mcp.run()
