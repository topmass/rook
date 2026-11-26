"""Gather the owner's agent inbox on demand: open PRs, T3 threads that need them, and waiting work entries.

Read only: no background polling, no side effects, no state written. Standard library only, so relay.py
and Rook's Python can both run it. Run `python desktop/agent_inbox.py --check` to test with fake JSON.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time

import desk
import settings
import watch
import work
OWNER = settings.OWNER_TOKEN  # The owner's name, filled in when the text leaves Rook.

ROOT = Path(__file__).resolve().parent.parent
PROJECTS_FILE = settings.CONFIG.with_name("skills") / "workspace/SKILL.md"  # The owner's private projects table.
PROJECT_ROW = re.compile(r"^\|\s*([^|`]+?)\s*\|\s*`([^`]+)`\s*\|\s*([^|]+?)\s*\|\s*([^|]*)\|", re.M)
TIMEOUT_SECONDS = 15.0
SHOW_TIMEOUT_SECONDS = 10.0
REMOTE_WORKERS = 6
LOCAL_WORKERS = 5
STALE_DAYS = 30
STALE_SECONDS = STALE_DAYS * 86400
GITHUB_LOGIN_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})")

PR_QUERY_TEMPLATE = """
query {
  search(query: "is:pr is:open author:%s", type: ISSUE, first: 50) {
    nodes {
      ... on PullRequest {
        number
        title
        url
        isDraft
        updatedAt
        headRefName
        reviewDecision
        repository { nameWithOwner }
        commits(last: 1) {
          nodes {
            commit {
              statusCheckRollup { state }
            }
          }
        }
      }
    }
  }
}
""".strip()

CI_STATES = {
    "SUCCESS": "passing",
    "FAILURE": "failing",
    "ERROR": "failing",
    "PENDING": "pending",
    "EXPECTED": "pending",
}

REVIEW_LABELS = {
    "APPROVED": "approved",
    "CHANGES_REQUESTED": "changes requested",
}

QUESTION_WORDS = frozenset({"question", "questions", "input", "ask", "userinput", "askuserquestion"})
PERMISSION_WORDS = frozenset({"permission", "permissions", "approval", "approve", "approvals"})
UNKNOWN_KIND = "a question or permission"

UNREACHABLE_HINTS = (
    "connection refused",
    "connection timed out",
    "could not resolve",
    "no route to host",
    "network is unreachable",
    "operation timed out",
    "broken pipe",
    "permission denied",
    "no running t3 code server",
    "timed out",
)


def projects_by_machine(path=PROJECTS_FILE):
    """Parse the projects table into {machine: [(title, path), ...]}, or {} without one."""
    try:
        text = Path(path).read_text()
    except OSError:
        return {}
    grouped = {}
    for title, folder, machine, _ in PROJECT_ROW.findall(text):
        key = machine.strip().lower()
        grouped.setdefault(key, []).append((title.strip(), folder.strip()))
    return grouped


def parse_iso(stamp):
    """Parse an ISO-8601 UTC timestamp to a Unix timestamp, or None."""
    if not isinstance(stamp, str) or not stamp.strip():
        return None
    try:
        return datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def updated_age_ts(ts, now):
    """Format a Unix timestamp as 'updated 3 days ago'."""
    if ts is None:
        return "updated unknown"
    seconds = max(0.0, now - ts)
    if seconds < 60:
        return "updated just now"
    for unit, size in (("day", 86400), ("hour", 3600), ("minute", 60)):
        if seconds >= size:
            count = int(seconds // size)
            return f"updated {count} {unit}{'s' if count != 1 else ''} ago"
    return "updated just now"


def updated_age(stamp, now):
    """Format an ISO timestamp as 'updated 3 days ago'."""
    return updated_age_ts(parse_iso(stamp), now)


def _gh_binary():
    return desk.find_tool("gh") or "gh"


def _pr_query(author):
    return PR_QUERY_TEMPLATE % author


def _github_author(run_cmd, deadline):
    """Return (login, error): github_user setting if configured, else signed-in gh account login."""
    saved = settings.read_settings()[0]
    configured = (saved.get("github_user") or "").strip()
    if configured and GITHUB_LOGIN_RE.fullmatch(configured):
        return configured, None
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return None, "github: could not reach"
    code, out, err = run_cmd([_gh_binary(), "api", "user", "-q", ".login"], remaining)
    if code:
        lower = f"{err}\n{out}".lower()
        if code == 4 or "gh auth login" in lower:
            return None, "github: signed out. Run gh auth login."
        return None, "github: could not reach"
    login = out.strip().splitlines()[0].strip() if out.strip() else ""
    if not GITHUB_LOGIN_RE.fullmatch(login):
        return None, "github: unreadable response"
    return login, None


def _run_cmd(argv, timeout):
    """Run argv with no stdin and a timeout. Return (returncode, stdout, stderr)."""
    try:
        done = subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=max(0.5, timeout),
        )
        return done.returncode, done.stdout, done.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "timed out"
    except OSError as exc:
        return 127, "", str(exc)


def _t3_argv(machines_table, machine, *args):
    if machines_table is None:
        return watch.t3_on(machine, *args)
    entry = machines_table.get(machine)
    if not entry:
        return None
    prefix = entry.get("run") or []
    cmd = (entry["t3"], *args)
    return [*prefix, shlex.join(cmd)] if prefix else list(cmd)


def _is_unreachable(returncode, stderr):
    lower = (stderr or "").lower()
    return returncode in (124, 127, 255) or any(hint in lower for hint in UNREACHABLE_HINTS)


def _classify_kind(raw):
    words = set(re.findall(r"[a-z]+", raw.lower()))
    if words & QUESTION_WORDS:
        return "question"
    if words & PERMISSION_WORDS:
        return "permission"
    return None


def request_kind(thread):
    """Return 'question', 'permission', or a plain fallback when the thread JSON omits the kind."""
    for key in ("pendingRequestKind", "requestKind"):
        raw = thread.get(key)
        if isinstance(raw, str):
            kind = _classify_kind(raw)
            if kind:
                return kind
    pending = thread.get("pendingRequests")
    if isinstance(pending, list):
        for item in pending:
            if not isinstance(item, dict):
                continue
            for key in ("kind", "type"):
                raw = item.get(key)
                if isinstance(raw, str):
                    kind = _classify_kind(raw)
                    if kind:
                        return kind
    return UNKNOWN_KIND


def _normalize_pr_url(url):
    return url.strip().rstrip("/").lower() if isinstance(url, str) and url.strip() else ""


def _thread_pr_urls(thread):
    """Pull request URLs linked to a thread in t3 thread list JSON."""
    urls = []
    linked = thread.get("linkedPullRequest")
    if isinstance(linked, str):
        urls.append(linked)
    elif isinstance(linked, dict) and linked.get("url"):
        urls.append(linked["url"])
    for item in thread.get("pullRequests") or ():
        if isinstance(item, str):
            urls.append(item)
        elif isinstance(item, dict) and item.get("url"):
            urls.append(item["url"])
    return [_normalize_pr_url(u) for u in urls if _normalize_pr_url(u)]


def parse_pull_requests(payload, now):
    """Convert raw gh GraphQL JSON into normalized PR dicts."""
    nodes = (((payload or {}).get("data") or {}).get("search") or {}).get("nodes") or []
    prs = []
    for node in nodes:
        if not isinstance(node, dict) or not node.get("number"):
            continue
        repo = (node.get("repository") or {}).get("nameWithOwner") or ""
        commits = ((node.get("commits") or {}).get("nodes") or [])
        rollup = {}
        if commits and isinstance(commits[-1], dict):
            rollup = (commits[-1].get("commit") or {}).get("statusCheckRollup") or {}
        raw_ci = (rollup.get("state") or "").upper()
        ci = CI_STATES.get(raw_ci, "none")
        is_draft = bool(node.get("isDraft"))
        updated_at = node.get("updatedAt") or ""
        prs.append({
            "repo": repo,
            "number": int(node["number"]),
            "title": (node.get("title") or "").strip(),
            "url": node.get("url") or "",
            "draft": is_draft,
            "state": "draft" if is_draft else "ready",
            "ci": ci,
            "review_decision": node.get("reviewDecision") or None,
            "head_ref": node.get("headRefName") or "",
            "updated_at": updated_at,
            "age": updated_age(updated_at, now),
            "thread": None,
        })
    return prs


def _pr_sort_key(pr):
    # Ready PRs wait on the owner's review first, then PRs with failing CI, then drafts.
    tier = 1 if pr["ci"] == "failing" else 2 if pr["draft"] else 0
    ts = parse_iso(pr["updated_at"]) or 0.0
    return (tier, -ts, pr["repo"], pr["number"])


def _fetch_prs(run_cmd, deadline, now):
    author, author_error = _github_author(run_cmd, deadline)
    if author_error:
        return [], author_error
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return [], "github: could not reach"
    argv = [_gh_binary(), "api", "graphql", "-f", f"query={_pr_query(author)}"]
    code, out, err = run_cmd(argv, remaining)
    if code:
        lower = f"{err}\n{out}".lower()
        if code == 4 or "gh auth login" in lower:
            return [], "github: signed out. Run gh auth login."
        return [], "github: could not reach"
    try:
        payload = json.loads(out)
    except ValueError:
        return [], "github: unreadable response"
    if payload.get("errors") and not (payload.get("data") or {}).get("search"):
        return [], "github: could not reach"
    return parse_pull_requests(payload, now), None


def _needs_show_check(thread):
    """Whether a listed thread without pendingRequestCount might be waiting for its owner."""
    if "pendingRequestCount" in thread:
        return False
    if thread.get("settled"):
        return False
    status = thread.get("status")
    if status == "running":
        return True
    if status == "waiting" and not thread.get("pendingBackgroundTasks"):
        return True
    return False


def _fetch_machine_threads(machine, machines_table, custom_machines, projects, run_cmd, deadline, show_timeout):
    """List threads across one machine's projects in parallel, then check active threads with thread show."""
    if not projects:
        return [], None, False
    is_remote = bool(machines_table[machine].get("run"))
    workers = min(REMOTE_WORKERS if is_remote else LOCAL_WORKERS, len(projects))
    list_unreachable = threading.Event()
    listed = {}
    ok_projects = 0
    failed_projects = 0

    def list_one(project_title, project_path):
        if list_unreachable.is_set():
            return project_title, project_path, None, "skipped"
        remaining = deadline - time.monotonic()
        if remaining <= 0.5:
            list_unreachable.set()
            return project_title, project_path, None, "timed out"
        argv = _t3_argv(custom_machines, machine, "thread", "list", "--project", project_path, "--json")
        if not argv:
            return project_title, project_path, None, "unknown machine"
        code, out, err = run_cmd(argv, remaining)
        if code:
            if _is_unreachable(code, err):
                list_unreachable.set()
                return project_title, project_path, None, "unreachable"
            return project_title, project_path, None, (err or "").strip() or f"exit {code}"
        try:
            rows = json.loads(out)
        except ValueError:
            return project_title, project_path, None, "unreadable json"
        if not isinstance(rows, list):
            return project_title, project_path, None, "unexpected json"
        return project_title, project_path, rows, None

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(list_one, title, path) for title, path in projects]
        for fut in as_completed(futures):
            project_title, project_path, rows, error = fut.result()
            if error is not None:
                failed_projects += 1
                continue
            ok_projects += 1
            for row in rows:
                if not isinstance(row, dict) or not row.get("threadId"):
                    continue
                if row.get("archived"):
                    continue
                tid = row["threadId"]
                prev = listed.get(tid)
                # Prefer the more specific project path when a parent folder also lists a thread.
                if prev is None or len(project_path) > len(prev[1]):
                    listed[tid] = (project_title, project_path, dict(row))

    if ok_projects == 0:
        return [], f"{machine}: could not reach", True

    # t3 thread list omits pendingRequestCount on current t3 builds; check every active candidate with its own budget.
    # Sort oldest first so a thread that stopped updating while waiting for the owner runs first.
    candidates = [
        tid for tid, (_, _, t) in sorted(
            listed.items(), key=lambda pair: parse_iso(pair[1][2].get("updatedAt")) or 0.0
        )
        if _needs_show_check(t)
    ]

    unchecked_threads = 0
    if candidates:
        show_deadline = time.monotonic() + show_timeout
        show_unreachable = threading.Event()

        def show_one(tid):
            if show_unreachable.is_set():
                return tid, None
            remaining = show_deadline - time.monotonic()
            if remaining <= 0.5:
                show_unreachable.set()
                return tid, None
            argv = _t3_argv(custom_machines, machine, "thread", "show", tid, "--messages", "0", "--json")
            if not argv:
                return tid, None
            code, out, err = run_cmd(argv, remaining)
            if code:
                if _is_unreachable(code, err):
                    show_unreachable.set()
                return tid, None
            try:
                detail = json.loads(out)
            except ValueError:
                return tid, None
            full = detail.get("thread") if isinstance(detail, dict) else None
            return tid, full if isinstance(full, dict) else None

        with ThreadPoolExecutor(max_workers=max(1, min(workers, len(candidates)))) as pool:
            for tid, full in pool.map(show_one, candidates):
                if full is not None:
                    listed[tid][2].update(full)
                else:
                    unchecked_threads += 1

    notes = []
    if unchecked_threads:
        notes.append(f"{unchecked_threads} active thread{'s' if unchecked_threads != 1 else ''} not checked")
    if failed_projects:
        notes.append(f"{failed_projects} project{'s' if failed_projects != 1 else ''} not read")
    error = f"{machine}: {', '.join(notes)}" if notes else None

    result = [(machine, project_title, thread) for project_title, _, thread in listed.values()]
    return result, error, False


def _fetch_work(work_path, now):
    try:
        data = work.load(work_path)
    except work.Unreadable as exc:
        return [], f"work list: {exc}"
    # Match work.catch_up: both waiting and unsent drafted entries wait on the owner.
    waiting = [e for e in data["entries"] if work.is_open(e) and e.get("state") in ("waiting", "drafted")]
    waiting.sort(key=lambda e: (0 if e["state"] == "waiting" else 1, -(e.get("changed") or 0)))
    items = []
    for entry in waiting:
        state = entry["state"]
        items.append({
            "id": entry["id"],
            "machine": entry.get("machine") or watch.local_machine(),
            "project": entry.get("project") or "No project",
            "wish": entry.get("wish") or "",
            "state": state,
            "waits_on": entry.get("waits_on") or ("drafted and not sent" if state == "drafted" else settings.render(OWNER)),
            "thread": entry.get("thread"),
            "changed": entry.get("changed"),
            "age": updated_age_ts(entry.get("changed"), now),
        })
    return items, None


def _explicit_count(thread):
    raw = thread.get("pendingRequestCount")
    if isinstance(raw, int) and not isinstance(raw, bool):
        return raw
    return None


def _gather_core(
    *,
    now=None,
    timeout=TIMEOUT_SECONDS,
    show_timeout=None,
    projects_path=PROJECTS_FILE,
    work_path=None,
    machines=None,
    run_cmd=None,
):
    """Gather open PRs, T3 threads, and waiting work entries in parallel. Return (public_data, meta)."""
    now = time.time() if now is None else float(now)
    run_cmd = _run_cmd if run_cmd is None else run_cmd
    machines_table = watch.machines() if machines is None else machines
    by_machine = projects_by_machine(projects_path)
    active_machines = [m for m in machines_table if by_machine.get(m)]
    deadline = time.monotonic() + timeout
    per_show_timeout = min(timeout, SHOW_TIMEOUT_SECONDS) if show_timeout is None else float(show_timeout)

    prs = []
    all_threads = []
    work_items = []
    errors = []
    failed_sources = {}
    unreachable_machines = set()

    with ThreadPoolExecutor(max_workers=len(active_machines) + 2) as pool:
        pr_fut = pool.submit(_fetch_prs, run_cmd, deadline, now)
        work_fut = pool.submit(_fetch_work, work_path, now)
        machine_futs = {
            m: pool.submit(
                _fetch_machine_threads, m, machines_table, machines, by_machine[m], run_cmd, deadline, per_show_timeout
            )
            for m in active_machines
        }

        prs, pr_err = pr_fut.result()
        if pr_err:
            errors.append(pr_err)
            failed_sources["github"] = pr_err

        work_items, work_err = work_fut.result()
        if work_err:
            errors.append(work_err)
            failed_sources["work"] = work_err

        for m in active_machines:
            threads_on_m, m_err, unreachable = machine_futs[m].result()
            all_threads.extend(threads_on_m)
            if m_err:
                errors.append(m_err)
                failed_sources[m] = m_err
            if unreachable:
                unreachable_machines.add(m)

    # Link PRs to T3 threads by PR URL from t3 thread list's pullRequests and linkedPullRequest fields.
    url_to_thread = {}
    for _, _, thread in sorted(all_threads, key=lambda item: parse_iso(item[2].get("updatedAt")) or 0.0, reverse=True):
        title = (thread.get("title") or thread.get("threadId") or "").strip()
        for url in _thread_pr_urls(thread):
            if url not in url_to_thread:
                url_to_thread[url] = title

    for pr in prs:
        key = _normalize_pr_url(pr.get("url"))
        if key and key in url_to_thread:
            pr["thread"] = url_to_thread[key]

    prs.sort(key=_pr_sort_key)

    needs_threads = []
    observed_threads = []
    for machine, project, thread in all_threads:
        updated_at = thread.get("updatedAt") or ""
        count = _explicit_count(thread)
        parent = watch.parent_of(thread, machine)
        observed_threads.append({
            "machine": machine,
            "project": project,
            "thread_id": thread["threadId"],
            "title": (thread.get("title") or thread["threadId"]).strip(),
            "kind": request_kind(thread),
            "pending_count": count,
            "parent_thread": parent[1] if parent else None,
            "run_id": thread.get("activeRunId") or thread.get("latestRunId") or None,
            "updated_at": updated_at,
        })
        if watch.classify(thread) != "needs":
            continue
        needs_threads.append({
            "machine": machine,
            "project": project,
            "thread_id": thread["threadId"],
            "title": (thread.get("title") or thread["threadId"]).strip(),
            "kind": request_kind(thread),
            "pending_count": int(thread.get("pendingRequestCount") or 0),
            "updated_at": updated_at,
            "age": updated_age(updated_at, now),
        })
    needs_threads.sort(key=lambda item: (-(parse_iso(item["updated_at"]) or 0.0), item["machine"], item["thread_id"]))

    data = {
        "threads": needs_threads,
        "work": work_items,
        "pull_requests": prs,
        "errors": errors,
    }
    meta = {
        "all_threads": observed_threads,
        "failed_sources": failed_sources,
        "unreachable_machines": unreachable_machines,
    }
    return data, meta


def gather(
    *,
    now=None,
    timeout=TIMEOUT_SECONDS,
    show_timeout=None,
    projects_path=PROJECTS_FILE,
    work_path=None,
    machines=None,
    run_cmd=None,
):
    """Gather open PRs, T3 threads needing the owner, and waiting work entries in parallel."""
    data, _ = _gather_core(
        now=now,
        timeout=timeout,
        show_timeout=show_timeout,
        projects_path=projects_path,
        work_path=work_path,
        machines=machines,
        run_cmd=run_cmd,
    )
    return data


def gather_for_sync(
    *,
    now=None,
    timeout=TIMEOUT_SECONDS,
    show_timeout=None,
    projects_path=PROJECTS_FILE,
    work_path=None,
    machines=None,
    run_cmd=None,
):
    """Gather inbox data plus full thread counts and failed sources for mailbox sync."""
    return _gather_core(
        now=now,
        timeout=timeout,
        show_timeout=show_timeout,
        projects_path=projects_path,
        work_path=work_path,
        machines=machines,
        run_cmd=run_cmd,
    )


def check_pr_state(pr_ref, *, run_cmd=None, timeout=SHOW_TIMEOUT_SECONDS):
    """Ask gh for the current state of one pull request. Return a dict or None on failure."""
    if "#" not in pr_ref:
        return None
    repo, num = pr_ref.rsplit("#", 1)
    if not repo or not num.isdigit():
        return None
    runner = _run_cmd if run_cmd is None else run_cmd
    argv = [
        _gh_binary(), "pr", "view", num, "--repo", repo,
        "--json", "state,title,url,isDraft,updatedAt",
    ]
    code, out, _ = runner(argv, timeout)
    if code:
        return None
    try:
        data = json.loads(out)
    except ValueError:
        return None
    return data if isinstance(data, dict) and isinstance(data.get("state"), str) else None


def check_thread_state(machine, thread_id, *, machines=None, run_cmd=None, timeout=SHOW_TIMEOUT_SECONDS):
    """Ask t3 thread show for one thread. Return its thread dict or None on failure."""
    runner = _run_cmd if run_cmd is None else run_cmd
    argv = _t3_argv(machines, machine, "thread", "show", thread_id, "--messages", "0", "--json")
    if not argv:
        return None
    code, out, _ = runner(argv, timeout)
    if code:
        return None
    try:
        detail = json.loads(out)
    except ValueError:
        return None
    thread = detail.get("thread") if isinstance(detail, dict) else None
    return thread if isinstance(thread, dict) else None


def pr_ref_of(pr):
    repo = (pr.get("repo") or "").strip().lower()
    number = pr.get("number")
    return f"{repo}#{int(number)}" if repo and number is not None else ""


def apply_overlays(data, overlays, *, show_all=False):
    """Filter ignored or snoozed pull requests out of data. Return (filtered_data, hidden_counts)."""
    if not overlays or show_all:
        return data, {"ignored": 0, "snoozed": 0}
    kept = []
    hidden = {"ignored": 0, "snoozed": 0}
    for pr in data.get("pull_requests") or []:
        overlay = overlays.get(pr_ref_of(pr))
        if overlay and overlay.get("state") == "dismissed":
            hidden["ignored"] += 1
            continue
        if overlay and overlay.get("state") == "snoozed":
            hidden["snoozed"] += 1
            continue
        kept.append(pr)
    return {**data, "pull_requests": kept}, hidden


def _pr_line(pr, overlay=None):
    parts = [f"{pr['repo']}#{pr['number']}", pr["state"], f"CI {pr['ci']}"]
    review = REVIEW_LABELS.get(pr.get("review_decision"))
    if review:
        parts.append(review)
    if overlay and overlay.get("state") in ("dismissed", "snoozed"):
        parts.append("ignored" if overlay["state"] == "dismissed" else "snoozed")
    parts.append(pr["title"])
    if pr.get("thread"):
        parts.append(f"thread: {pr['thread']}")
    parts.append(pr["age"])
    return "- " + " | ".join(parts)


def _thread_line(item):
    parts = [item["machine"], item["project"], item.get("kind") or UNKNOWN_KIND, f"{item['title']} ({item['thread_id']})", item["age"]]
    return "- " + " | ".join(parts)


def _work_line(item):
    status = "drafted and not sent" if item.get("state") == "drafted" else f"waiting on {item['waits_on']}"
    project = item.get("project") or "No project"
    where = project if item["machine"] == watch.local_machine() else f"{project} on {item['machine']}"
    parts = [where, f'"{item["wish"]}"', status, item["age"]]
    return "- " + " | ".join(parts) + f" [id {item['id']}]"


def _pr_age_seconds(pr, now):
    ts = parse_iso(pr.get("updated_at"))
    return max(0.0, now - ts) if ts is not None else None


def format_inbox(data, now=None, *, hidden_prs=None, pr_overlays=None):
    """Format gathered inbox data compactly: T3 threads, waiting work, ready PRs, failing CI, drafts, stale PRs."""
    now = time.time() if now is None else float(now)
    threads = data.get("threads") or []
    work_items = data.get("work") or []
    prs = data.get("pull_requests") or []
    errors = data.get("errors") or []
    overlays = pr_overlays or {}

    fresh_prs = []
    stale_ages = []
    for pr in prs:
        age_sec = _pr_age_seconds(pr, now)
        if age_sec is not None and age_sec > STALE_SECONDS:
            stale_ages.append(age_sec)
        else:
            fresh_prs.append(pr)

    ready_prs = [pr for pr in fresh_prs if not pr["draft"] and pr["ci"] != "failing"]
    failing_prs = [pr for pr in fresh_prs if pr["ci"] == "failing"]
    draft_prs = [pr for pr in fresh_prs if pr["draft"] and pr["ci"] != "failing"]

    sections = []
    if threads:
        sections.append(settings.render(f"T3 threads needing {OWNER}") + f" ({len(threads)}):\n" + "\n".join(_thread_line(t) for t in threads))
    if work_items:
        sections.append(settings.render(f"Work waiting on {OWNER}") + f" ({len(work_items)}):\n" + "\n".join(_work_line(w) for w in work_items))
    if ready_prs:
        sections.append(f"Ready PRs ({len(ready_prs)}):\n" + "\n".join(_pr_line(pr, overlays.get(pr_ref_of(pr))) for pr in ready_prs))
    if failing_prs:
        sections.append(f"PRs with failing CI ({len(failing_prs)}):\n" + "\n".join(_pr_line(pr, overlays.get(pr_ref_of(pr))) for pr in failing_prs))
    if draft_prs:
        sections.append(f"Draft PRs ({len(draft_prs)}):\n" + "\n".join(_pr_line(pr, overlays.get(pr_ref_of(pr))) for pr in draft_prs))
    if stale_ages:
        oldest_days = int(max(stale_ages) // 86400)
        count = len(stale_ages)
        if count == 1:
            sections.append(f"1 PR untouched for over {STALE_DAYS} days, {oldest_days} days old")
        else:
            sections.append(f"{count} PRs untouched for over {STALE_DAYS} days, oldest {oldest_days} days")

    if not sections:
        sections.append("Inbox is empty.")
    if hidden_prs:
        ignored = hidden_prs.get("ignored", 0)
        snoozed = hidden_prs.get("snoozed", 0)
        hidden_parts = []
        if ignored:
            hidden_parts.append(f"{ignored} pull request{'s' if ignored != 1 else ''} ignored")
        if snoozed:
            noun = "snoozed" if ignored else f"pull request{'s' if snoozed != 1 else ''} snoozed"
            hidden_parts.append(f"{snoozed} {noun}")
        if hidden_parts:
            sections.append(", ".join(hidden_parts))
    if errors:
        sections.append("\n".join(errors))
    return "\n\n".join(sections)


def check():
    """Self-check with fake gh and t3 JSON. No network, no real state."""
    now = datetime(2026, 11, 24, 12, 0, 0, tzinfo=timezone.utc).timestamp()

    def iso_ago(seconds):
        return datetime.fromtimestamp(now - seconds, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    fake_machines = {
        "oak": {"environmentId": "env-oak", "run": [], "t3": "t3", "code": "/home/alice/Code"},
        "nimbus-pc": {
            "environmentId": "env-nimbus",
            "run": ["ssh", "bob@remote"],
            "t3": "/home/bob/.local/bin/t3",
            "code": "/home/bob/Code",
        },
    }

    # Whole-word kind classification: "task" must not match "ask".
    assert _classify_kind("task") is None
    assert _classify_kind("background_task") is None
    assert _classify_kind("question") == "question"
    assert _classify_kind("user_input") == "question"
    assert _classify_kind("approval_request") == "permission"
    assert request_kind({"pendingRequestKind": "task"}) == UNKNOWN_KIND
    assert request_kind({"pendingRequestCount": 1}) == UNKNOWN_KIND

    with tempfile.TemporaryDirectory() as folder:
        scratch = Path(folder)
        projects_md = scratch / "projects.md"
        projects_md.write_text(
            "| Project | Path | Machine | Aliases | T3 project id |\n"
            "|---|---|---|---|---|\n"
            "| rook | `/home/alice/Code/rook` | oak | rook | p-oak |\n"
            "| dashboards | `/home/bob/Code/dashboards` | nimbus-pc | dr | p-nimbus |\n"
            "| mempact | `/home/bob/Code/mempact` | nimbus-pc | mem | p-mem |\n"
        )
        work_file = scratch / "work.json"
        work_data = work.empty()
        e1 = work.add(work_data, {"wish": "pick a chart style", "project": "dashboards", "machine": "nimbus-pc",
                                  "thread": "t-dr-1"}, "rook", now - 3600)
        work.change(e1, {"state": "waiting", "waits_on": work.DECISION + "Line or bar chart?"}, "watcher", now - 3600)
        work.add(work_data, {"wish": "unsent draft wish", "project": "rook", "machine": "oak"}, "rook", now - 2400)
        e3 = work.add(work_data, {"wish": "still building", "project": "rook", "machine": "oak"}, "rook", now - 1800)
        work.change(e3, {"state": "running"}, "watcher", now - 1800)
        e4 = work.add(work_data, {"wish": "already closed", "project": "rook", "machine": "oak"}, "rook", now - 7200)
        work.change(e4, {"state": "waiting", "waits_on": OWNER}, "watcher", now - 7200)
        e4["closed"] = now - 600
        work.save(work_data, work_file)

        fake_gh = {
            "data": {
                "search": {
                    "nodes": [
                        {
                            "number": 10,
                            "title": "Passing ready PR",
                            "url": "https://github.com/example/rook/pull/10",
                            "isDraft": False,
                            "updatedAt": iso_ago(3 * 86400 + 60),
                            "headRefName": "feat/clean-logs",
                            "reviewDecision": "APPROVED",
                            "repository": {"nameWithOwner": "example/rook"},
                            "commits": {"nodes": [{"commit": {"statusCheckRollup": {"state": "SUCCESS"}}}]},
                        },
                        {
                            "number": 11,
                            "title": "Draft pending PR",
                            "url": "https://github.com/example/rook/pull/11",
                            "isDraft": True,
                            "updatedAt": iso_ago(2 * 3600),
                            "headRefName": "feat/agent-inbox",
                            "reviewDecision": None,
                            "repository": {"nameWithOwner": "example/rook"},
                            "commits": {"nodes": [{"commit": {"statusCheckRollup": {"state": "PENDING"}}}]},
                        },
                        {
                            "number": 12,
                            "title": "Failing CI PR",
                            "url": "https://github.com/example/rook/pull/12",
                            "isDraft": False,
                            "updatedAt": iso_ago(7200),
                            "headRefName": "fix/broken-check",
                            "reviewDecision": "CHANGES_REQUESTED",
                            "repository": {"nameWithOwner": "example/rook"},
                            "commits": {"nodes": [{"commit": {"statusCheckRollup": {"state": "FAILURE"}}}]},
                        },
                        {
                            "number": 13,
                            "title": "No CI PR",
                            "url": "https://github.com/example/rook/pull/13",
                            "isDraft": False,
                            "updatedAt": iso_ago(5 * 60),
                            "headRefName": "docs/readme",
                            "reviewDecision": None,
                            "repository": {"nameWithOwner": "example/rook"},
                            "commits": {"nodes": [{"commit": {"statusCheckRollup": None}}]},
                        },
                        {
                            "number": 14,
                            "title": "Old draft PR",
                            "url": "https://github.com/example/rook/pull/14",
                            "isDraft": True,
                            "updatedAt": iso_ago(116 * 86400 + 60),
                            "headRefName": "old/turnstile",
                            "reviewDecision": None,
                            "repository": {"nameWithOwner": "example/rook"},
                            "commits": {"nodes": [{"commit": {"statusCheckRollup": {"state": "SUCCESS"}}}]},
                        },
                        {
                            "number": 15,
                            "title": "Old ready PR",
                            "url": "https://github.com/example/rook/pull/15",
                            "isDraft": False,
                            "updatedAt": iso_ago(45 * 86400 + 60),
                            "headRefName": "old/cleanup",
                            "reviewDecision": None,
                            "repository": {"nameWithOwner": "example/rook"},
                            "commits": {"nodes": [{"commit": {"statusCheckRollup": {"state": "SUCCESS"}}}]},
                        },
                    ]
                }
            }
        }

        # Fake list rows match real t3 thread list JSON: linkedPullRequest and pullRequests, no branch field.
        oma_threads = [
            {
                "threadId": "t-oak-q",
                "title": "Build agent inbox",
                "status": "running",
                "pendingRequestCount": 1,
                "pendingRequestKind": "question",
                "linkedPullRequest": {"url": "https://github.com/example/rook/pull/11"},
                "pullRequests": [],
                "updatedAt": iso_ago(300),
                "parentThreadId": None,
                "archived": False,
                "settled": False,
            },
            {
                "threadId": "t-oak-sub",
                "title": f"Subagent waiting on {OWNER}",
                "status": "running",
                "pendingRequestCount": 1,
                "linkedPullRequest": None,
                "pullRequests": [],
                "updatedAt": iso_ago(60),
                "parentThreadId": "t-oak-q",
                "archived": False,
                "settled": False,
            },
            {
                "threadId": "t-oak-archived",
                "title": "Archived ignored",
                "status": "running",
                "pendingRequestCount": 1,
                "linkedPullRequest": None,
                "pullRequests": [],
                "updatedAt": iso_ago(30),
                "parentThreadId": None,
                "archived": True,
                "settled": False,
            },
            {
                "threadId": "t-oak-show",
                "title": "Fix broken check thread",
                "status": "running",
                "linkedPullRequest": None,
                "pullRequests": [{"url": "https://github.com/example/rook/pull/12", "number": 12, "state": "open"}],
                "updatedAt": iso_ago(120),
                "parentThreadId": None,
                "archived": False,
                "settled": False,
            },
        ]
        oma_show = {
            "thread": {
                "threadId": "t-oak-show",
                "title": "Fix broken check thread",
                "status": "running",
                "pendingRequestCount": 1,
                "updatedAt": iso_ago(120),
            },
            "messages": [],
        }
        nimbus_threads = [
            {
                "threadId": "t-nimbus-perm",
                "title": "Deploy staging",
                "status": "running",
                "pendingRequestCount": 1,
                "pendingRequestKind": "permission",
                "linkedPullRequest": None,
                "pullRequests": [],
                "updatedAt": iso_ago(900),
                "parentThreadId": None,
                "archived": False,
                "settled": False,
            },
            {
                "threadId": "t-nimbus-idle",
                "title": "Dashboards Orchestrator",
                "status": "completed",
                "pendingRequestCount": 0,
                "linkedPullRequest": None,
                "pullRequests": [{"url": "https://github.com/example/rook/pull/10", "number": 10, "state": "open"}],
                "updatedAt": iso_ago(1800),
                "parentThreadId": None,
                "archived": False,
                "settled": False,
            },
        ]

        # 1. Full check: section order, subagent kept, archived skipped, CI states, URL link, stale collapse, work drafted.
        gh_queries = []

        def fake_run(argv, timeout):
            joined = " ".join(argv)
            if Path(argv[0]).name == "gh":
                if "user" in argv:
                    return 0, "octocat\n", ""
                gh_queries.append(joined)
                return 0, json.dumps(fake_gh), ""
            if argv[0] == "ssh":
                if "/home/bob/Code/dashboards" in joined:
                    return 0, json.dumps(nimbus_threads), ""
                return 0, "[]", ""
            if "show" in argv and "t-oak-show" in argv:
                return 0, json.dumps(oma_show), ""
            return 0, json.dumps(oma_threads), ""

        data = gather(now=now, projects_path=projects_md, work_path=work_file, machines=fake_machines, run_cmd=fake_run)
        assert gh_queries and "author:octocat" in gh_queries[0], gh_queries
        assert not data["errors"], data["errors"]
        assert [t["thread_id"] for t in data["threads"]] == [
            "t-oak-sub", "t-oak-show", "t-oak-q", "t-nimbus-perm"
        ], data["threads"]
        assert [t["kind"] for t in data["threads"]] == [
            UNKNOWN_KIND, UNKNOWN_KIND, "question", "permission"
        ], data["threads"]
        assert [w["id"] for w in data["work"]] == [1, 2], data["work"]
        assert [w["state"] for w in data["work"]] == ["waiting", "drafted"], data["work"]
        # JSON keeps all PRs, sorted: ready (13, 10, 15), failing CI (12), draft (11, 14).
        assert [pr["number"] for pr in data["pull_requests"]] == [13, 10, 15, 12, 11, 14], data["pull_requests"]
        by_num = {pr["number"]: pr for pr in data["pull_requests"]}
        assert (by_num[10]["ci"], by_num[11]["ci"], by_num[12]["ci"], by_num[13]["ci"]) == (
            "passing", "pending", "failing", "none"
        )
        assert (by_num[10]["state"], by_num[11]["state"]) == ("ready", "draft")
        assert by_num[10]["age"] == "updated 3 days ago", by_num[10]["age"]
        assert by_num[10]["thread"] == "Dashboards Orchestrator", by_num[10]
        assert by_num[11]["thread"] == "Build agent inbox", by_num[11]
        assert by_num[12]["thread"] == "Fix broken check thread", by_num[12]
        assert by_num[13]["thread"] is None

        text = format_inbox(data, now=now)
        assert text.index(settings.render(f"T3 threads needing {OWNER} (4):")) < text.index(settings.render(f"Work waiting on {OWNER} (2):"))
        assert text.index(settings.render(f"Work waiting on {OWNER} (2):")) < text.index("Ready PRs (2):")
        assert text.index("Ready PRs (2):") < text.index("PRs with failing CI (1):")
        assert text.index("PRs with failing CI (1):") < text.index("Draft PRs (1):")
        assert text.index("Draft PRs (1):") < text.index("2 PRs untouched for over 30 days, oldest 116 days")
        assert "Old draft PR" not in text and "Old ready PR" not in text
        assert "thread: Dashboards Orchestrator" in text
        assert "thread: Build agent inbox" in text
        assert "thread: Fix broken check thread" in text
        assert "drafted and not sent" in text
        assert "[id 1]" in text and "[id 2]" in text and "#1 |" not in text and "#2 |" not in text, text
        assert UNKNOWN_KIND in text
        assert "updated 3 days ago" in text
        assert "CI passing" in text and "CI failing" in text and "CI pending" in text and "CI none" in text
        json.dumps(data)

        # 2. Unreachable machine: one line, no crash, other sources stay intact.
        def unreachable_run(argv, timeout):
            if argv[0] == "ssh":
                return 255, "", "ssh: connect to host 198.51.100.10 port 22: Connection timed out"
            return fake_run(argv, timeout)

        partial = gather(now=now, projects_path=projects_md, work_path=work_file, machines=fake_machines, run_cmd=unreachable_run)
        assert partial["errors"] == ["nimbus-pc: could not reach"], partial["errors"]
        assert len(partial["pull_requests"]) == 6 and len(partial["threads"]) == 3
        partial_text = format_inbox(partial, now=now)
        assert partial_text.count("nimbus-pc: could not reach") == 1, partial_text

        # 3. Partial failure: 1 project fails and 1 active thread show fails -> reported explicitly, never silent.
        nimbus_active = [
            {
                "threadId": "t-nimbus-run-1",
                "title": "Active thread 1",
                "status": "running",
                "linkedPullRequest": None,
                "pullRequests": [],
                "updatedAt": iso_ago(600),
                "parentThreadId": None,
                "archived": False,
                "settled": False,
            },
            {
                "threadId": "t-nimbus-run-2",
                "title": "Active thread 2",
                "status": "running",
                "linkedPullRequest": None,
                "pullRequests": [],
                "updatedAt": iso_ago(300),
                "parentThreadId": None,
                "archived": False,
                "settled": False,
            },
        ]

        def partial_fail_run(argv, timeout):
            joined = " ".join(argv)
            if argv[0] == "ssh":
                if "thread list" in joined and "/home/bob/Code/dashboards" in joined:
                    return 0, json.dumps(nimbus_active), ""
                if "thread list" in joined and "/home/bob/Code/mempact" in joined:
                    return 1, "", "project not found"
                if "thread show" in joined and "t-nimbus-run-1" in joined:
                    return 0, json.dumps({"thread": {**nimbus_active[0], "pendingRequestCount": 1}}), ""
                if "thread show" in joined and "t-nimbus-run-2" in joined:
                    return 1, "", "show failed"
            return fake_run(argv, timeout)

        degraded = gather(
            now=now, projects_path=projects_md, work_path=work_file, machines=fake_machines, run_cmd=partial_fail_run
        )
        assert degraded["errors"] == ["nimbus-pc: 1 active thread not checked, 1 project not read"], degraded["errors"]
        assert any(t["thread_id"] == "t-nimbus-run-1" for t in degraded["threads"]), degraded["threads"]

        # 4. Signed-out gh: exit 4 / gh auth login message.
        def signed_out_run(argv, timeout):
            if Path(argv[0]).name == "gh":
                return 4, "", "To get started with GitHub CLI, please run:  gh auth login"
            return 0, "[]", ""

        signed_out = gather(
            now=now, projects_path=projects_md, work_path=scratch / "none.json", machines=fake_machines, run_cmd=signed_out_run
        )
        assert signed_out["errors"] == ["github: signed out. Run gh auth login."], signed_out["errors"]

        # 5. Empty inbox.
        empty_work = scratch / "empty_work.json"

        def empty_run(argv, timeout):
            if Path(argv[0]).name == "gh":
                if "user" in argv:
                    return 0, "octocat\n", ""
                return 0, json.dumps({"data": {"search": {"nodes": []}}}), ""
            return 0, "[]", ""

        blank = gather(now=now, projects_path=projects_md, work_path=empty_work, machines=fake_machines, run_cmd=empty_run)
        assert blank == {"threads": [], "work": [], "pull_requests": [], "errors": []}, blank
        assert format_inbox(blank, now=now) == "Inbox is empty.", format_inbox(blank, now=now)

    print("Agent inbox: all checks passed.")


def main():
    if sys.argv[1:] == ["--check"]:
        return check()
    data = gather()
    if sys.argv[1:] == ["--json"]:
        print(json.dumps(data, indent=2))
    else:
        print(format_inbox(data))


if __name__ == "__main__":
    main()
