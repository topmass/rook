// Rook's tools for its Pi session. pi_harness.py passes Rook's tool servers as JSON in ROOK_PI_SERVERS, in the shape
// of an mcp.json "mcpServers" object, and the core tools' names, in order, in ROOK_PI_CORE.
// Every server tool has codemode exposure: never declared on its own, but callable. This extension declares the core
// ones once, before the first request, and the declared list never changes after: a server that connects late is
// reached with execute_tool for the rest of the session. The model reaches every other tool with search_tools and
// execute_tool, so a local model server never reads the whole conversation again.
import { createHash } from "crypto";

const LIMIT = 8000; // Characters of tool output the model gets back from one execute_tool call, all blocks together.
// How long the first request waits for core server tools, as Pi waits for direct tools. The harness check sets less.
const WAIT_MS = Number(process.env.ROOK_PI_WAIT_MS) || 10000;
// Pi's server list in the prompt names its codemode tool, which Rook does not load.
const PI_SERVERS_LINE = "Call the tools of `codemode` servers from codemode scripts.";
const ROOK_SERVERS_LINE = "Call their tools with execute_tool, and find them with search_tools.";

export default function (pi: any) {
  const servers = JSON.parse(process.env.ROOK_PI_SERVERS || "{}");
  const core: string[] = JSON.parse(process.env.ROOK_PI_CORE || "[]");
  for (const [name, config] of Object.entries(servers)) pi.registerMcpServer(name, config);
  let declared: string[] | null = null;
  let toolsHash: string | null = null;
  let first = true;

  // Pi reports a server tool's codemode exposure as deferred when its own codemode tool is not loaded.
  const callable = () => pi.getAllTools().filter((tool: any) => ["codemode", "deferred"].includes(tool.exposure) && tool.name.startsWith("mcp__"));

  pi.on("before_agent_start", async () => {
    if (declared === null) {
      const deadline = Date.now() + WAIT_MS;
      const known = () => new Set(pi.getAllTools().map((tool: any) => tool.name));
      while (core.some((name) => !known().has(name)) && Date.now() < deadline) await new Promise((r) => setTimeout(r, 100));
      const have = known();
      declared = core.filter((name) => have.has(name));
      const late = [...new Set(core.filter((name) => !have.has(name)).map((name) => name.split("__")[1]))];
      for (const server of late)
        process.stderr.write(`pi: ${server}'s tools were not ready at the start, so this session reaches them with execute_tool.\n`);
    }
    if ([...pi.getActiveTools()].sort().join() !== [...declared].sort().join()) pi.setActiveTools(declared);
  });

  pi.on("before_provider_request", (event: any) => {
    const hash = createHash("sha256").update(JSON.stringify(event.payload?.tools ?? null)).digest("hex");
    if (toolsHash !== null && hash !== toolsHash)
      process.stderr.write("pi: the declared tool list changed mid-session, so the model server reads the whole conversation again.\n");
    toolsHash = hash;
    const text = JSON.stringify(event.payload); // The same swap at every request, so the prompt stays the same.
    if (first && !text.includes(PI_SERVERS_LINE) && !text.includes(ROOK_SERVERS_LINE) && text.includes("<mcp_servers>"))
      process.stderr.write("pi: Pi's server list no longer has the line Rook rewrites, so check what it tells the model.\n");
    first = false;
    return text.includes(PI_SERVERS_LINE) ? JSON.parse(text.split(PI_SERVERS_LINE).join(ROOK_SERVERS_LINE)) : undefined;
  });

  pi.registerTool({
    name: "search_tools",
    label: "Search tools",
    exposure: "model-only", // The model calls it; execute_tool cannot.
    description: "Find Rook's other tools by what they do. Returns each match's name, what it does, and its arguments.",
    parameters: { type: "object", properties: {
      query: { type: "string", description: "Words for what you need, such as \"thread pull request\"." },
      limit: { type: "integer", minimum: 1, maximum: 10, description: "At most this many matches. Default 5." },
    }, required: ["query"] },
    reachesTools: () => "all",
    async execute(_id: string, params: any) {
      const words = String(params.query || "").toLowerCase().split(/[^a-z0-9]+/).filter((word) => word.length > 1);
      const active = new Set(pi.getActiveTools());
      // ponytail: plain word count over name, description and argument names; BM25 if it misses at hundreds of tools.
      const hits = callable().filter((tool: any) => !active.has(tool.name)).map((tool: any) => {
        const text = `${tool.name} ${tool.description} ${Object.keys(tool.parameters?.properties || {}).join(" ")}`.toLowerCase();
        return { tool, score: words.filter((word) => text.includes(word)).length };
      }).filter((hit: any) => hit.score > 0).sort((a: any, b: any) => b.score - a.score)
        .slice(0, Math.min(Math.max(Number(params.limit) || 5, 1), 10));
      const text = hits.length ? hits.map(({ tool }: any) => `${tool.name}(${cut(shape(tool.parameters), 300)}): ${sentence(tool.description)}`).join("\n")
        : `No tool matches "${cut(String(params.query), 100)}". Rook has no tool for that.`;
      return { content: [{ type: "text", text }], details: {} };
    },
  });

  pi.registerTool({
    name: "execute_tool",
    label: "Execute tool",
    exposure: "model-only", // The model calls it; it cannot call itself or search_tools.
    description: "Run one of Rook's tools that is not in your list, by its full name, such as mcp__render__show_scene, with its arguments as a JSON object.",
    parameters: { type: "object", properties: {
      name: { type: "string", description: "The tool's full name, from a skill or from search_tools." },
      arguments: { description: "The tool's arguments, as a JSON object." },
    }, required: ["name"] },
    reachesTools: (input: any) => [String(input?.name ?? "")],
    async execute(_id: string, params: any, signal: any, _update: any, ctx: any) {
      const name = String(params.name ?? "");
      let args = params.arguments ?? {};
      if (typeof args === "string") {
        try { args = JSON.parse(args); } catch { /* refused below */ }
      }
      const refuse = (text: string) => ({ content: [{ type: "text", text }], details: {}, isError: true });
      if (declared?.includes(name)) return refuse(`${name} is in your tool list: call it directly.`);
      if (typeof args !== "object" || args === null || Array.isArray(args))
        return refuse("The arguments must be a JSON object, such as {\"threadId\": \"abc\"}.");
      const call = await ctx.executeTool(name, args, { signal });
      let room = LIMIT, dropped = 0;
      const content: any[] = [];
      for (const block of call.result?.content ?? []) {
        if (block.type !== "text") content.push(block);
        else if (room <= 0) dropped += Array.from(String(block.text)).length;
        else {
          const text = cut(String(block.text), room);
          room -= Array.from(text).length;
          content.push({ ...block, text });
        }
      }
      if (dropped) content.push({ type: "text", text: `…${dropped} more characters cut…` });
      const first = content[0]?.text ?? "";
      if (call.isError && (first.startsWith("Tool ") || first.startsWith("Validation failed")))
        content.push({ type: "text", text: "Use search_tools to find the right name and arguments." });
      return { content, details: {}, isError: Boolean(call.isError) };
    },
  });
}

function cut(text: string, limit: number) {
  const points = Array.from(text); // Code points, so a cut never splits a character.
  if (points.length <= limit) return text;
  const tail = Math.min(2000, Math.floor(limit / 4));
  return `${points.slice(0, limit - tail).join("")}\n…${points.length - limit} characters cut…\n${points.slice(-tail).join("")}`;
}

function sentence(text: string) {
  return cut(String(text || "").split(/(?<=\.)\s/)[0], 200);
}

function shape(schema: any) {
  const required = new Set(schema?.required || []);
  return Object.entries(schema?.properties || {}).slice(0, 12).map(([key, value]: [string, any]) =>
    `${cut(key, 40)}${required.has(key) ? "" : "?"}: ${type(value)}`).join(", ");
}

function type(value: any): string {
  if (value?.enum) return value.enum.slice(0, 6).map((item: any) => cut(JSON.stringify(item), 30)).join("|") + (value.enum.length > 6 ? "|…" : "");
  if (value?.type === "array") return `${type(value.items)}[]`;
  if (Array.isArray(value?.type)) return value.type.join("|");
  if (value?.anyOf) return value.anyOf.slice(0, 4).map(type).join("|");
  return value?.type || "any";
}
