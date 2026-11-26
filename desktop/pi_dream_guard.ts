// The guard of Rook's nightly memory tidy under Pi. Pi has no permission modes, so each tool call goes through
// memory.py's dream guard, the one Antigravity's tidy uses: reads stay in the memory folder, and writes are flat .md
// notes there. memory.py passes the guard's argv as JSON in ROOK_DREAM_GUARD. Any failure blocks the call.
import { execFileSync } from "node:child_process";

const NAMES: Record<string, string> = { read: "read_file", write: "write_file", edit: "edit_file",
  find: "find_by_name", ls: "list_dir" };  // Pi's tools by the guard's names. Any other tool is denied.

export default function (pi: any) {
  const argv: string[] = JSON.parse(process.env.ROOK_DREAM_GUARD || "[]");
  pi.on("tool_call", async (event: any) => {
    try {
      const call = { toolCall: { name: NAMES[event.toolName] ?? event.toolName, args: event.input } };
      const out = JSON.parse(execFileSync(argv[0], argv.slice(1), { input: JSON.stringify(call), encoding: "utf8" }));
      if (out.decision !== "allow") return { block: true, reason: out.reason || "Memory dream guard denied it." };
    } catch (error) {
      return { block: true, reason: `Memory dream guard failed: ${error}` };
    }
  });
}
