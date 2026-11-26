# The brief

A brief is the message Rook sends to a thread. The agent that reads it never heard ⟦owner⟧ and never saw ⟦his⟧ screen, so the brief carries everything Rook knows. A good brief lets the agent start without asking anything. It is plain text, not markdown, so that any model reads it the same way. Most briefs run 15 to 30 lines.

## Rules

- **Quote ⟦owner⟧'s words exactly** as the transcript gave them. Builders work from ⟦his⟧ words, and a paraphrase has misled them before.
- **Name the outcome and what done looks like,** such as "a draft PR with CI green" or "a plan for ⟦owner⟧ to approve, no code yet". When ⟦owner⟧ did not say, choose the smallest done that answers ⟦him⟧, and mark it as your reading.
- **Give your reading** separately, and mark what you assumed.
- **Describe the screenshot in words.** The thread cannot see it. Name the window's class and title, and write the error text, the file name, or the values it showed.
- **Say what you checked** and how, and what you did not check.
- **List the constraints.** ⟦owner⟧'s own come first, such as "do not push anything" or "one PR". The standing ones follow, as in the template.
- **Copy the project's rules** from the workspace skill word for word, with the default rule: "Deploy" means the project's default target, never production, unless ⟦owner⟧ says "production".
- **Fill the "Only" lines** of the template only when they apply. "Authorized by:" quotes another person's approval, such as "merge ready, merge in this order", so the thread does not wait for them again. "Decision rule:" holds ⟦owner⟧'s handover in ⟦his⟧ words, such as "have Opus decide, come to me when merged".
- **Point to related threads** by title, machine, and id, when one holds history the agent needs.
- **End with the report-back paragraph** for the thread's machine.

## Template

Leave out `Work <N> on Rook's list.` for a Rook build handoff with `--work`, because `relay.py` adds it.

```text
From Rook, ⟦owner⟧'s voice assistant on <this machine>. ⟦Owner⟧ asked by voice, so ⟦his⟧ words come from speech recognition and may hold mishearings. Treat this as ⟦owner⟧'s own request. Work <N> on Rook's list. <For a continued thread: "This is a new request in this thread." or "This continues the work above.">

⟦Owner⟧ said: "<the transcript, word for word>"

Goal: <the outcome in one sentence>. Done means: <what ⟦owner⟧ will see when it is finished>.

Rook's reading: <one or two sentences, with assumptions marked, such as "I assume 'acme' means the acme-demo project.">

What Rook saw and checked: <"A screenshot of <class>: <title>. It showed <the error, the values, the file>." or "No screenshot."> <Facts Rook checked, or "Nothing yet.">

Project rules: <the default rule and the project's rules from the workspace skill, word for word>
<Only for a shipping order: ⟦Owner⟧ confirmed: "<⟦his⟧ yes>" to Rook's read-back: <repository, pull requests or change, environment>.>
<Only when given: Authorized by: <sender>, in <where Rook saw it>: "<their message>". This is the approval.>
<Only when given: Decision rule: ⟦Owner⟧ said "<⟦his⟧ words>". It ends with this batch, and never covers production or destructive steps. Ask ⟦owner⟧ for those.>

Constraints: <⟦owner⟧'s stated constraints.> <For code work: "Work on a new branch or worktree named for this task. Never commit to main."> <When another task runs in the same repository: "Another task works in this repository now, so use a new worktree."> <For a visible change: "Take a screenshot or a short clip of the result, and name its full path in the Show line."> Follow the global and project AGENTS.md and the project's own instructions and skills. You are the main agent: orchestrate subagents as ⟦owner⟧'s model rules say, and verify their work yourself. <A model line from models.md when ⟦owner⟧ named a model.> Make routine choices yourself. Ask ⟦owner⟧ only about decisions that change scope, risk, or behavior. Ask before anything destructive, any push or merge ⟦he⟧ did not ask for, and anything that touches production.

<Report-back paragraph>
```

## Report-back paragraphs

Both paragraphs end with the proof lines below, copied in place of `<Proof lines>`.

For a thread on this machine, use this paragraph, with the command copied from SKILL.md:

```text
When you finish, and whenever you need ⟦owner⟧ to decide or answer something, tell Rook in two or three plain sentences that will be read aloud. Name the work in plain words and never write a work number in anything you tell Rook. Say what happened, and what ⟦owner⟧ has to do, if anything:
/usr/bin/python <the relay.py path from SKILL.md> tell "<two or three plain sentences, then the proof lines>"
Write no markdown or code in the sentences. If the command fails, Rook is not running. Carry on without it.
Keep your entry on Rook's list current: run /usr/bin/python <the relay.py path from SKILL.md> work update <N> --state running when you start, and work update <N> --state live --commit <hash> --try "<what ⟦owner⟧ should try>" once it is in use.
<Proof lines>
```

For a thread on another machine, which cannot reach Rook's inbox, use this one:

```text
You run on <its machine>, so you cannot reach Rook's inbox or work list on <this machine>. Rook keeps your work entry. When you finish, and whenever you stop to wait for ⟦owner⟧, end your message with a last paragraph that starts with "For Rook:" and holds two or three plain sentences that will be read aloud. Name the work in plain words and never write a work number in that paragraph. Say what happened, and what ⟦owner⟧ has to do, if anything. Write no markdown or code in the sentences.
<Proof lines>
```

The proof lines:

```text
End it with these short lines, each one even when empty. Only Links and Show hold links or paths.
Tested: <what you ran, and what it showed>
Not tested: <what you did not check>
Links: <pull request, branch, or commit>
Deployed to: <none, staging, or production>
Show: <full path to a screenshot or clip, or none>
Decision needed: <the question for ⟦owner⟧, or none>
```

## Fresh main thread

When ⟦owner⟧ asks for a new thread with no task, such as "start up a Fable thread in this project", the thread becomes the project's new main thread. ⟦Owner⟧ opens those with an orientation and a wait. Replace the Goal line with this:

```text
Goal: You are a fresh main thread for <project> on <machine>. Get situated: read the global and project AGENTS.md, the project's specsheet and memory notes, and its recent state, such as the branch and open PRs. Then reply with a short summary of where the project stands, and wait for ⟦owner⟧'s first task. Change nothing yet.
```

## New project

For the first thread of a new project, replace the Goal line with this:

```text
Goal: Start the new project <name> in <folder> on <machine>. The folder exists and is a T3 project<", with a git repository" when you passed --git>. Work only inside it. ⟦Owner⟧'s idea: <⟦his⟧ words, restated in one or two sentences>. Done means: <for example "a running hello world and a short README with the next steps">. You run the show on the details and ask ⟦owner⟧ only about direction.
```

## Example

```text
From Rook, ⟦owner⟧'s voice assistant on desk. ⟦Owner⟧ asked by voice, so ⟦his⟧ words come from speech recognition and may hold mishearings. Treat this as ⟦owner⟧'s own request. Work 7 on Rook's list. This is a new request in this thread.

⟦Owner⟧ said: "the acme demo invoice pdf is rounding the totals wrong again can you get someone on that"

Goal: Find why invoice PDF totals round wrongly and fix it. Done means: a draft PR with the fix, CI green, and the cause explained.

Rook's reading: I assume "acme demo" means the acme-demo project and "again" means an earlier fix did not hold.

What Rook saw and checked: A screenshot of chromium: Invoice 1042 - Acme Demo. The PDF preview showed line items of 19.995 and 4.005 with a total of 24.01. Rook checked nothing else.

Project rules: "Deploy" means the project's default target, never production, unless ⟦owner⟧ says "production".

Constraints: Work on a new branch or worktree named for this task. Never commit to main. Take a screenshot of the fixed PDF, and name its full path in the Show line. Follow the global and project AGENTS.md and the project's own instructions and skills. You are the main agent: orchestrate subagents as ⟦owner⟧'s model rules say, and verify their work yourself. Make routine choices yourself. Ask ⟦owner⟧ only about decisions that change scope, risk, or behavior. Ask before anything destructive, any push or merge ⟦he⟧ did not ask for, and anything that touches production.

You run on server, so you cannot reach Rook's inbox or work list on desk. Rook keeps your work entry. When you finish, and whenever you stop to wait for ⟦owner⟧, end your message with a last paragraph that starts with "For Rook:" and holds two or three plain sentences that will be read aloud. Name the work in plain words and never write a work number in that paragraph. Say what happened, and what ⟦owner⟧ has to do, if anything. Write no markdown or code in the sentences.
End it with these short lines, each one even when empty. Only Links and Show hold links or paths.
Tested: <what you ran, and what it showed>
Not tested: <what you did not check>
Links: <pull request, branch, or commit>
Deployed to: <none, staging, or production>
Show: <full path to a screenshot or clip, or none>
Decision needed: <the question for ⟦owner⟧, or none>
```
