# Shared agent memory

Portable per-project memory with a nightly dreaming loop, vendored in Rook and installed into `~/.agents/`.

Sources behind this design:
- Anthropic: [The components of agent memory](https://www.anthropic.com/research/components-of-agent-memory)
- Anthropic cookbook: [Dreaming with a dynamic workflow](https://platform.claude.com/cookbook/managed-agents-cma-dreaming-with-a-dynamic-workflow)
- Meta: [Self-Improving Memory](https://facebookresearch.github.io/RAM/blogs/self_improving_memory/)

## Layout
- Each project keeps flat Markdown notes and a `MEMORY.md` index in `<project>/.agent-memory/` (ignored globally by Git).
- For a multi-repo project, list its umbrella folder in `PROJECT_ROOTS` inside `~/.agents/memory.conf` by hand.
- `hooks/memory-context.sh` runs standalone at session start and prints the memory folder and index.
- `bin/dream` runs nightly via `agent-dream.timer` (`Persistent=true`, `Nice=10`), skips idle projects and empty nights, and runs uncapped by default (with an optional `DREAM_MAX_RUNS` cap in `memory.conf`).
- `bin/remember` files a single note using `MEMORY_MODEL`; `bin/memory-dir` resolves a folder's memory path.

## Manage from Rook
- Install: `relay.py memory install-shared`
- Remove: `relay.py memory remove-shared` (removes installed files, hooks, and timer; leaves all memory notes in place)
