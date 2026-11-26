// Rook's tool servers for its Pi session. pi_harness.py passes them as JSON in ROOK_PI_SERVERS, in the shape of an
// mcp.json "mcpServers" object. Pi has no command-line flag for MCP servers, so this extension registers them.
export default function (pi: any) {
  const servers = JSON.parse(process.env.ROOK_PI_SERVERS || "{}");
  for (const [name, config] of Object.entries(servers)) pi.registerMcpServer(name, config);
}
