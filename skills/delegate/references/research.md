# Research runs

Research goes through T3, like all other agent work. Each run is a new thread in one research project, which the workspace skill names with its machine and ids. Without one, ask ⟦owner⟧ once which project should hold research runs. Only you decide what to remember from a result.

## When it is research

- **Research** is ⟦owner⟧ wanting something found out, compared, or checked, with nothing built or changed. Examples: "which of these two libraries is better maintained", "find out what changed in the last release".
- **Questions about Rook itself are research too,** such as where its voices come from, or which models or tools it uses. Only changes to Rook, and diagnoses of its code, go to the build thread.
- **Not research:** a question you can answer in your own turn in a few seconds. Answer it yourself.
- **Not research:** work on a project's code, even a code investigation. It stays with that project's thread, as SKILL.md says.

## Starting a run

1. **Tidy up first.** Call `t3_thread_list` with the research project's `environmentId` and `projectId`, `settled: false`, `includeSubagents: false`, and `limit: 10`. Settle each finished one with `t3_thread_organize`, `action: "settle"`, its `threadId`, and the `environmentId`. Leave a thread that is running or waits for ⟦owner⟧.
2. **Launch a new thread** with `t3_thread_launch` in the research project: its `projectId` and `environmentId`, and the machine's `runtimeMode` when the workspace skill gives one. Give it a title of three to six words that names the question, a new `clientRequestId`, and the model for research runs from ⟦owner⟧'s preferences file, as models.md says. Any provider can run research. A request with several parts still goes whole to one thread. That thread decides by itself whether to use subagents.
3. **Tell ⟦owner⟧** in one short sentence that research is under way, such as "I've got a research thread on the server looking into that." Do not say aloud that it steered or started a turn.

## The research brief

Use brief.md's rules and template, with these lines in place of Goal and Constraints:

```text
Goal: Research this question and report: <the question in one or two sentences>. A good answer contains: <for example "a recommendation with the two or three facts that decide it" or "a yes or no, with the source">.

Constraints: Only read and report. Change no file outside this project's folder, open no pull request, push nothing, and save no memory note. Mark every statement as verified, with its source, or as inferred, or as unknown. Your last message is the whole report, because Rook reads only that message, not the thread's history. Keep it under 400 words.
```

End with the report-back paragraph from brief.md for the research project's machine. Its "For Rook:" paragraph holds the answer in two or three sentences.

## Hearing back

The thread watcher reports when the run finishes, as for any thread you start. Then do all of this in that one turn:

1. **Read the report:** `t3_thread_read` with `view: "messages"`, `beforePosition` set to the thread's `itemCount`, `limit: 1`, and `maxCharsPerItem: 4000`.
2. **Tell ⟦owner⟧ the answer** in your usual spoken form. Say what is verified and what is not.
3. **Decide what to save.** Save only what is worth keeping, with the memory command you already use. Say what you saved in the written part.
4. **Settle the thread** with `t3_thread_organize`, `action: "settle"`, its `threadId`, and the `environmentId`.

A follow-up on the same subject, while it is fresh in the conversation, may go to that thread with `t3_thread_send` and `mode: "auto"`, settled or not. Settle it again when you report that answer. Otherwise, start a new run.

You settle only threads in the research project. Never settle one that is running or waits for ⟦owner⟧.

## Dives

A dive is a research run you start on your own, as the system prompt says. ⟦Owner⟧ has already heard your answer.

1. **Skip the tidy-up.** You tidy up when you hear back.
2. **Check for a running dive.** Load `t3_thread_list` and `t3_thread_launch` together. Call `t3_thread_list` with the `environmentId`, the `projectId`, `titleContains: "Dive: "`, `statuses: ["preparing", "queued", "starting", "running", "waiting"]`, `includeSubagents: false`, and `limit: 1`. When it returns a thread, start no dive and say nothing about it. Still write the repeat in step 4.
3. **Launch** as in step 2 of Starting a run. The title starts with `Dive: `, then three to six words that name the topic. In the brief's Goal, the question is how to improve your suggestion. Give ⟦owner⟧'s words and your suggestion. A good answer contains "a better suggestion with the two or three facts behind it, or no better idea, with the reason". The Constraints stay as they are.
4. **After the check or the launch,** write the repeat of your spoken paragraph that the system prompt asks for. Say nothing more.

When the watcher reports a dive, follow Hearing back with one change. In step 2, speak only if the report gives ⟦owner⟧ a real improvement or something new. Otherwise answer PASS, which is silence. When ⟦owner⟧ has moved on, answer PASS too. Then do the tidy-up from step 1 of Starting a run.
