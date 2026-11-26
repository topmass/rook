# A new project

⟦Owner⟧ starts fresh ventures by voice, such as "on the other machine we need a new project, we're gonna start something fresh". A new project's folder is `<projects folder>/<name>`. On this machine the projects folder is the `projects_folder` setting, chosen in onboarding. Elsewhere, and while it is unset, it is the machine table's code folder. The command below picks it, so you need not look it up.

## Choose the name and machine

- **The name** is the one ⟦owner⟧ says, in lower case with hyphens, such as `voice-notes`. When ⟦verb:he names|they name⟧ none, pick a short name from the idea, and say it in your answer.
- **The machine** is the one ⟦verb:he names|they name⟧. With none named, use the machine the workspace skill gives for new projects, unless the work is about this desktop. Without a workspace skill, use this machine.
- **Check the name** with `t3_project_list` on that machine. When a project with that name exists, say so and ask whether to use it.
- **Git.** Pass `--git` when ⟦owner⟧ asks for a repository, or when the project is code that will grow. Leave it out for a quick experiment.

## Create it

Use the same command on every machine. It runs `t3 project add` on the machine itself, so it works where the T3 tools may not change projects. It also creates the folder and the repository, and it is safe to run again for a project that already exists.

`/usr/bin/python ${CLAUDE_PLUGIN_ROOT}/../desktop/relay.py project new <name> --machine <machine> [--git]`

Copy the path exactly as SKILL.md shows it. Pass `--path <folder>` only when ⟦owner⟧ names a different folder. The default is `<projects folder>/<name>` on that machine.

On success the command prints one line: `created <machine> <project-id> <path>`, or `exists <machine> unknown-id <path>` when that folder already is a project. After an `exists` line, find the project id with `t3_project_list` on that machine by its `workspaceRoot`. When T3 already has the project but its folder was missing, the command removes the folder it made and fails. Then tell ⟦owner⟧ that the project is listed in T3 but its folder is gone on that machine, and ask whether to use another name or have ⟦him⟧ restore the folder. The command refuses a folder that already holds files and is not a project, so pick another name then. On any failure it exits with a message and takes back what it made. Tell ⟦owner⟧ that message in one sentence, and launch nothing. Always pass `--machine`, because the command's default is this machine.

On this machine only, when the command itself is missing or broken, `t3_project_create` with this machine's `environmentId`, `title`, `workspaceRoot`, and `createWorkspaceRootIfMissing: true` does the same job without git. On a machine whose link may not change projects there is no fallback, because the T3 tools return `capability_denied` there.

When the `orchestrator` setting is `herdr`, there is no T3 project to make: start the first agent in `<projects folder>/<name>` with `relay.py herdr start`, as the rook:herdr skill shows. With `pi` or `none`, say that new projects need T3 Code or Herdr today.

## Start the first thread

1. Call `t3_thread_launch` with the machine's `environmentId`, the project id from the command, a title of three to six words, the model from models.md, and the "new project" brief from brief.md. Pass the machine's `runtimeMode` when the workspace skill gives one.
2. Tell ⟦owner⟧ in two sentences: the project's name and machine, and which model's thread is starting on it. End with "you'll hear when it's done".

## Cloning instead

When ⟦owner⟧ names an existing repository, create the project with the command as above, without `--git`, and tell the first thread in its brief to clone the repository into that folder. A clone through the T3 tools on a machine whose link may not change projects is untested and is likely denied like project creation.
