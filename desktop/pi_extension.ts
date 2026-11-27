// Rook's tools for its Pi session. pi_harness.py passes Rook's tool servers as JSON in ROOK_PI_SERVERS, in the shape
// of an mcp.json "mcpServers" object, and the core tools' names in ROOK_PI_CORE.
// Every server tool has codemode exposure: never declared on its own, but callable from a codemode script. This
// extension loads Pi's code mode without its models global, so a script cannot run models with the person's
// sign-ins. It declares the core once, before the first request, and the declared list never changes after: a server
// that connects late is reached from a script for the rest of the session, so a local model server never reads the
// whole conversation again.
import { createHash } from "crypto";
import { createCodemodeExtension } from "@earendil-works/pi-coding-agent";

// How long the first request waits for core server tools, as Pi waits for direct tools. The harness check sets less.
const WAIT_MS = Number(process.env.ROOK_PI_WAIT_MS) || 10000;
// Pi gives a script no deadline unless it asks for one, so one stuck in a loop would hold the turn. A script may still
// set its own; output stays within Pi's default of 10,000 tokens.
const SCRIPT_MS = Math.min(Number(process.env.ROOK_PI_SCRIPT_MS) || 120000, 120000); // The harness check sets less.
const OUTPUT_TOKENS = 10000;
const OPTIONS = /^\/\/ @options: (.*)\n?/;

export default function (pi: any) {
  const servers = JSON.parse(process.env.ROOK_PI_SERVERS || "{}");
  const core: string[] = JSON.parse(process.env.ROOK_PI_CORE || "[]");
  for (const [name, config] of Object.entries(servers)) pi.registerMcpServer(name, config);
  createCodemodeExtension({ models: false })(pi);
  let declared: string[] | null = null;
  let toolsHash: string | null = null;

  pi.on("before_agent_start", async () => {
    if (declared === null) {
      const deadline = Date.now() + WAIT_MS;
      const known = () => new Set(pi.getAllTools().map((tool: any) => tool.name));
      while (core.some((name) => !known().has(name)) && Date.now() < deadline) await new Promise((r) => setTimeout(r, 100));
      const have = known();
      declared = core.filter((name) => have.has(name));
      const late = [...new Set(core.filter((name) => !have.has(name)).map((name) => name.split("__")[1]))];
      for (const server of late)
        process.stderr.write(`pi: ${server}'s tools were not ready at the start, so this session reaches them from codemode scripts.\n`);
    }
    if ([...pi.getActiveTools()].sort().join() !== [...declared].sort().join()) pi.setActiveTools(declared);
  });

  pi.on("tool_call", (event: any) => {
    if (event.toolName !== "codemode" || typeof event.input?.code !== "string") return;
    const found = event.input.code.match(OPTIONS);
    let options: any = {};
    try {
      options = found ? JSON.parse(found[1]) : {};
    } catch {
      return; // Pi itself refuses a bad options line.
    }
    options.timeout_ms = Math.min(Number(options.timeout_ms) || SCRIPT_MS, SCRIPT_MS);
    options.max_output_tokens = Math.min(Number(options.max_output_tokens) || OUTPUT_TOKENS, OUTPUT_TOKENS);
    event.input.code = `// @options: ${JSON.stringify(options)}\n${found ? event.input.code.slice(found[0].length) : event.input.code}`;
  });

  pi.on("before_provider_request", (event: any) => {
    const hash = createHash("sha256").update(JSON.stringify(event.payload?.tools ?? null)).digest("hex");
    if (toolsHash !== null && hash !== toolsHash)
      process.stderr.write("pi: the declared tool list changed mid-session, so the model server reads the whole conversation again.\n");
    toolsHash = hash;
  });
}
