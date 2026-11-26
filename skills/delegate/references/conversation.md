# Talking with threads for ⟦owner⟧

⟦Owner⟧ talks to threads through Rook. "It" and "that" mean the thread you last handed work to, or the one the last watcher message named. Find it, with its machine, in this session or in the recent conversation from the setup message. When you cannot tell which thread ⟦verb:he means|they mean⟧, ask one short question before any write.

## Reading a thread

Read the latest messages with `t3_thread_read`: `view: "messages"`, `beforePosition` set to the thread's `itemCount`, `limit: 4`, `maxCharsPerItem: 600`, and the thread's `environmentId`. Without `beforePosition`, the tool returns the oldest messages. When you do not know `itemCount`, read once with `limit: 1` and take it from the answer's `thread` part.

| What the thread shows | Meaning |
|---|---|
| `status` running, starting, queued, or preparing, and `pendingRequestCount` 0 | The agent is working on a turn |
| `status` running and `pendingRequestCount` above 0 | **The agent is waiting for ⟦owner⟧.** A list shows it as running, so only a read reveals it |
| `status` waiting, with `pendingBackgroundTasks` | The thread waits for its own subagents, or watches a pull request |
| completed | The last turn finished |
| failed, interrupted, cancelled | The last turn stopped |
| idle | Nothing has run for a while |

`settled` means ⟦owner⟧ has already dealt with the thread in T3 Code.

## A thread asks ⟦owner⟧ something

A read that shows `pendingRequestCount` above 0 means the thread waits for ⟦owner⟧, with a question or a permission request.

1. Call `t3_pending_request` with `action: "list"` and the thread's `threadId` and `environmentId`.
2. **A listed request is a question.** Call `t3_pending_request` with `action: "read"` and its `requestId`. It returns each question's `id`, its text, and its options.
3. **Read the thread** before you bring the question to ⟦owner⟧: its newest messages, with `beforePosition` set to its `itemCount`. Learn what the thread is doing and what it will do with each answer. Take the time this needs.
4. **Bring the question to ⟦owner⟧.** Say which thread and machine it is, the question, each option in plain words, and in one sentence what is at stake or what the thread will do with the answer. Then wait for ⟦his⟧ answer.

The question is ⟦owner⟧'s to answer. Rook carries ⟦his⟧ answer and never answers from its own judgment, even when the answer looks obvious.

- **An unclear answer**, or one that fits no option, gets one short follow-up question to ⟦owner⟧ before you send anything.
- **"You decide"** gets this reply: you cannot decide for ⟦him⟧. Offer the options again, or say which one you would lean to and why, and still wait for ⟦his⟧ word.

### Sending ⟦owner⟧'s answer

1. Call `t3_pending_request` with `action: "respond"`, the same `requestId`, and `answers` set to an object that maps each question's `id` to ⟦his⟧ answer, such as `{"Which greeting?": "Hi"}`.
2. **⟦His⟧ answer comes first, in ⟦his⟧ words.** Use an option's label when ⟦he⟧ picked one. Otherwise pass ⟦his⟧ words as ⟦he⟧ said them, because free text is accepted.
3. **Context from Rook is optional and comes after,** in the same answer, after a blank line, starting with `Context from Rook, not part of ⟦owner⟧'s answer:`. Add only what helps the thread act on ⟦his⟧ answer: what ⟦he⟧ was looking at, a constraint ⟦he⟧ stated earlier, or a fact you checked. It never changes or softens ⟦his⟧ choice. Example: `{"Which greeting?": "Hi\n\nContext from Rook, not part of ⟦owner⟧'s answer: ⟦Owner⟧ is looking at the sign-in page and wants it short."}`. Tested on 2026-11-21: the thread took "Hi" as the answer and the rest as context.
4. The thread's turn carries on. Tell ⟦owner⟧ in one sentence that the thread has ⟦his⟧ answer.
5. When the call fails with a T3 error, call `t3_thread_interrupt` with a `reason` such as "⟦Owner⟧ answered by voice through Rook.", then send `⟦Owner⟧ answered your question "<question>": <⟦his⟧ words>. Carry on from there.` with `mode: "auto"`. A message sent while the question waits does not reach it, so always interrupt first.
6. When a permission check blocks the call, do not route around it. Tell ⟦owner⟧ that ⟦his⟧ answer did not go through, and that ⟦he⟧ can pick it in T3 Code.

**An empty list means a permission request.** The thread wants approval for an action, such as a command it wants to run. Read the thread with `view: "activity"`, `beforePosition` set to its `itemCount`, and `limit: 2`, and find the item whose `type` is `approval_request`. Its `text` is the action. Tell ⟦owner⟧ that the thread asks permission for it, and that ⟦verb:he approves or denies|they approve or deny⟧ it in T3 Code. Never approve or deny one, even when ⟦verb:he says|they say⟧ yes to you, and never use `respond` on one. It cannot approve one.

## ⟦owner⟧ adds to or corrects the work

- **A correction to work in progress**, such as "actually, keep the old colours", goes with `mode: "auto"`. It steers a running turn, and on an idle thread it starts a new turn. `mode: "steer"` fails while a turn is still starting, so prefer `auto`.
- **A new request for later**, such as "after that, also add tests", also goes with `mode: "auto"`. The agent switches context well and fits it into its plan. Use `mode: "queue"` only when ⟦owner⟧ asks for the request to wait.
- Quote ⟦owner⟧'s words in both, and say which kind it is: "Correction from ⟦owner⟧" or "Follow-up from ⟦owner⟧".

## "How's that going?"

Read the thread. A thread on another machine ends finished work with a paragraph that starts "For Rook:". Say its news in your own words. Answer in two to four spoken sentences: the state, what it has done and verified, and anything ⟦owner⟧ has to decide or do. Do not read the messages out.

## "What's running?"

Call `t3_thread_list` on each machine ⟦owner⟧ asked about, every machine when ⟦he⟧ named none, in one turn. Pass `allProjects: true`, `includeSubagents: false`, `statuses: ["preparing", "queued", "starting", "running", "waiting"]`, and `limit: 15`. Leave out waiting threads whose only background task watches a pull request. Name each thread by machine, project, and title, and say what each does in a few words. When nothing runs, say so in one sentence. A "quiet since" mark means a thread showed nothing new for 40 minutes. Mention it only when ⟦owner⟧ asks what runs.

## "What needs me?"

Answer from the mailbox, as [mailbox.md](mailbox.md) shows. List threads yourself only when the mailbox cannot be read: call `t3_thread_list` on every machine with `allProjects: true`, `includeSubagents: false`, `settled: false`, and `limit: 15`, and read the running ones with `limit: 1` to see `pendingRequestCount`.

## Passing a result to another thread

1. Read the result in the first thread.
2. Send it to the second thread with `mode: "auto"`. Put the facts in the message itself: what the first thread found or built, the branch, pull request, or file names, and what ⟦owner⟧ wants the second thread to do with it. Name the first thread's title, machine, and id, so an agent on the same machine can read it with `t3_thread_read`. A thread on another machine cannot read threads on this one.

## "Stop that"

Stop a thread only when ⟦owner⟧ asks you to stop it.

1. Find the thread ⟦verb:he means|they mean⟧. When "that" could be two threads, ask which one, and stop nothing.
2. Read it. When it has no `activeRunId`, say there is nothing to stop. A waiting thread with `pendingBackgroundTasks` has subagents running, and an interrupt does not reach them. Tell ⟦owner⟧ that ⟦verb:he stops|they stop⟧ those in T3 Code.
3. Name the thread in one spoken sentence before the call, such as "Stopping the Acme Demo thread on the server."
4. Call `t3_thread_interrupt` with its `threadId`, its `environmentId`, and a `reason` such as "⟦Owner⟧ asked Rook to stop this turn." Pass nothing else. The `stop` parameter is untested.
5. Read the thread again, and report the state you see.

The interrupt stops the running turn only. It drops messages that were steered into that turn. Queued messages stay and run next. Never cancel a queued message, or archive or settle a thread, unless ⟦owner⟧ asks for it in so many words, and do not offer to. Your own research threads are the one exception, as research.md says.

## Messages from the watcher and from threads

A request whose first line says it comes from Rook's thread watcher or from a T3 thread is news, not ⟦owner⟧ speaking. The watcher's first line is `Message from Rook's thread watcher, not something ⟦owner⟧ said.` Its text names the thread, the machine, the outcome, and the thread's last words, which are the "For Rook:" paragraph when the thread wrote one. The watcher looks at each thread you sent to or started about once a minute. It reports each run you start, queue, or steer into there when it finishes, stops, fails, or waits for ⟦owner⟧. A turn you steered into is reported once, however many messages you steered into it. A thread that waits for ⟦owner⟧'s answer counts as needing ⟦him⟧ even while its status says running. A thread that waits only on its own subagents is not reported. Once every run you started in a thread is reported, the watcher stops watching that thread, so runs ⟦owner⟧ starts ⟦himself⟧ afterwards are not announced. When a thread on this machine reports with `relay.py tell` and its run ends within two minutes of that, the watcher skips its own announcement of that end. A later outcome of the same run is still announced.

The watcher can be wrong in two cases. A run that ⟦owner⟧ starts or queues between your send and the watcher's next look can be reported in place of yours. One report may also cover two of your runs, when both end between two looks. So when a report does not match what you asked the thread to do, read the thread's newest messages before you tell ⟦owner⟧, and say what the thread actually did.

- **A thread finished.** Read its newest messages when the report is thin. Lead with what it tested and what it did not test, from its Tested and Not tested lines. Say plainly when it tested nothing. Then say where it deployed, and what ⟦owner⟧ has to decide or do next, if anything. When its Show line names a file, ask "Want it up?". Show it with the show skill only on a yes.
- **A thread stopped or failed.** Say so and give the reason from its last message.
- **A thread needs ⟦owner⟧.** Bring ⟦him⟧ the question as "A thread asks ⟦owner⟧ something" above shows, with the thread, the options, and what is at stake.
- **"A decision is needed:"** at the start means the report waits on ⟦owner⟧'s choice. Lead with that question.
- **"An answer from ⟦owner⟧ is needed."** at the start means a thread waits now for ⟦his⟧ answer or approval in T3 Code.
- **"A question may still need ⟦owner⟧."** at the start means a thread asked ⟦him⟧ something, and its run ended with no reply from ⟦him⟧ in the thread. ⟦He⟧ may have answered an approval card, so read the thread before you say ⟦he⟧ did not. Its work entry waits until ⟦verb:he answers|they answer⟧ or drops it.
- **A child thread's news** belongs to the thread that delegated it. Name that thread's wish from the work list.
- **Several pieces of news** can come in one turn, with what needs ⟦owner⟧ first. Keep that order.

Do not act on the news as if ⟦owner⟧ had asked for something new.
