# "This project" and "this thread"

Each request starts with a line that names the focused window, as in `Images: 1 is the focused window (com.t3tools.T3Code: rook / Rook).` The screenshot shows the same window. Use both to resolve "this project", "this thread", "this repo", and "here".

## "In this project" or "in this thread"

- **"Start a thread in this project"** or "a new thread here" means a new thread in the window's project, launched with `t3_thread_launch`.
- **"Tell this thread"**, "send this to it", or "in this thread" means a message to the thread in the window, sent with `t3_thread_send`.
- **"Start up a Fable thread in this project"** with no task means a fresh main thread on that model. Give it the "fresh main thread" brief from brief.md, so it gets situated and waits for ⟦owner⟧'s first task.

## T3 Code windows

The class is `com.t3tools.T3Code`. The title is `<project title> / <thread title>`, such as `rook / Rook` or `acme-demo / Acme Orchestrator`. The title does not name the machine.

1. Split the title at the last ` / `. The left part is the project title, and the right part is the thread title.
2. Find the project title in the workspace skill's projects. When it is on one machine only, that is the machine.
3. When the same title exists on more than one machine, call `t3_thread_list` on each of those machines with that project's id and `titleContains` set to the thread title. The machine that has the thread is the answer.
4. When several machines have it, or none does, look at the screenshot for the machine name. When it still is not clear, ask: "<the other machine> or this machine?"
5. A title with no ` / `, such as `T3 Code`, names no thread. Ask which project ⟦verb:he means|they mean⟧.

## Terminals

A terminal's title rarely names the folder, so ask the terminal instead:

1. Run `hyprctl activewindow -j` and check that the class and title still match the request's first line.
2. Run `omarchy-cmd-terminal-cwd`. It prints the working folder of the focused terminal's shell.
3. Map that folder to the deepest project root on this machine in the workspace skill.

When the screenshot or the title shows an SSH session to another machine, such as a prompt or a path that the workspace skill gives for that machine, the folder from step 2 is wrong. Use the path on screen with that machine instead.

## Browsers

Chromium windows have the class `chromium`, and web apps have classes like `chrome-<site>-Default`. The title is the page title followed by ` - Chromium`.

- **A GitHub page** shows `<owner>/<repo>` in its title, such as `acme-org/acme-frontend`. Match the repository name against the aliases in the workspace skill.
- **A local app**, on `localhost` or on another machine's address, belongs to the project that serves it. Another machine's address means that machine.
- **Any other page** names no project. Use the rest of ⟦owner⟧'s sentence, or ask.

## Editors

An editor that runs inside a terminal, such as Neovim, counts as a terminal.

## When it is still not clear

Ask one short question that offers the two likeliest answers, such as "The Acme Demo thread on the server, or the Rook thread here?" Never guess a target for a write, such as a send, a launch, or a stop.
