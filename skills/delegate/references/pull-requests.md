# Pull requests

Rook reads pull requests and their checks. It never merges, reviews, or changes one with its own tools. `pull_request_merge` stays denied. Never call `pull_request_create`, `pull_request_update`, `pull_request_review`, `pull_request_respond`, `ci_rerun`, or the link and watch tools either. Those belong to the project's threads.

## Reading

- **Find the repository** in `t3_project_list`: each project's `repositoryIdentity` has the GitHub owner and name.
- **`pull_request_read`** takes `repository` as `owner/name`, `number`, and `environmentId`. Pass `include: ["checks"]` for CI, or `["threads"]` for open review comments.
- **`ci_logs`** takes the same `repository` and `number`, and reads the tail of the failing checks.
- **`list_thread_pull_requests`** takes a `threadId` and lists the pull requests that thread made.
- **"What's open"** goes to `pull_request_list`. It lists the calling thread's repository, and Rook is no thread, so it may fail. Then run `gh pr list --repo <owner/name>` and `gh pr view` on this machine. Use `gh` only to read.

Say the number, the title, the author, the state, and the checks: passing, failing, or still running.

## A review

⟦Owner⟧ asks, for example, "get Sol to review 1438". Start a new thread in the project with `t3_thread_launch`, on the model ⟦verb:he names|they name⟧, or else on the model that SKILL.md step 3 picks for review work. Its brief gives the pull request link, the original brief or ⟦owner⟧'s words, and this goal: "Review this pull request read-only. Change no code, push nothing, and post nothing on GitHub. Report your findings." Its findings come to ⟦owner⟧. Fixes go to the project's main thread only on ⟦his⟧ word.

## A merge

A merge is a shipping order, so read it back first, as SKILL.md says: the repository, the pull request numbers, and the environment. After ⟦owner⟧'s yes, send it to the project's main thread with this line in the constraints:

```text
Before you merge, verify with GitHub that the signed-in account has administrator rights on the repository. Run the required checks. Stop and report on any failing check or open review finding. Merge only the pull requests named above. Deploy only where the read-back said.
```

When a third party approved the order, such as "merge ready, merge in this order", quote it in the "Authorized by:" line from brief.md.
