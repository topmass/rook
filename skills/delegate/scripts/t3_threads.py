#!/usr/bin/env python3
"""Show this machine's T3 Code threads in a few short lines. This is the fallback for when the T3 tools are missing.

t3_threads.py list [--days N] [--active] [PROJECT ...]   Top-level threads, newest first.
t3_threads.py needs [--days N]                           Threads that wait for an answer or failed.
t3_threads.py peek [--messages N] THREAD [THREAD ...]    The latest messages of each thread.

PROJECT is a path, a title, or an alias from the workspace skill's projects table. With none, the script reads
every project that table lists for this machine, and nothing when there is no table. It runs the t3 command once per project, in parallel.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys

# The owner's projects table lives in their private workspace skill, beside Rook's settings.
PROJECTS_FILE = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "rook/skills/workspace/SKILL.md"
BUSY = {"preparing", "queued", "starting", "running"}
# A row of the projects table: | title | `path` | machine | aliases |
ROW = re.compile(r"^\|\s*([^|`]+?)\s*\|\s*`([^`]+)`\s*\|\s*([^|]+?)\s*\|\s*([^|]*)\|", re.M)


def projects():
    """Return (title, path, machine, aliases) for each project row in the projects table, or none without one."""
    try:
        text = PROJECTS_FILE.read_text()
    except OSError:
        return []
    return [(t, str(Path(p).expanduser()), m.strip().lower(), a.lower()) for t, p, m, a in ROW.findall(text)]


def t3(*args):
    """Run t3 and return (output, error). The t3 command needs no shell."""
    try:
        run = subprocess.run(["t3", *args], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as error:
        return None, str(error)
    if run.returncode:
        return None, (run.stderr.strip().splitlines() or [f"t3 exited with {run.returncode}"])[-1]
    return run.stdout, None


def age(stamp):
    seconds = (datetime.now(timezone.utc) - datetime.fromisoformat(stamp.replace("Z", "+00:00"))).total_seconds()
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if seconds >= size:
            return f"{int(seconds // size)}{unit} ago"
    return "just now"


def days_old(stamp):
    return (datetime.now(timezone.utc) - datetime.fromisoformat(stamp.replace("Z", "+00:00"))).total_seconds() / 86400


def state(thread):
    """The thread's status, made plain where T3's word is ambiguous."""
    status = thread.get("status", "?")
    if status == "waiting" and (thread.get("pendingBackgroundTasks") or thread.get("blockedOnThreadWait")):
        return "working-on-subagents"
    return status


def resolve(names):
    """Map spoken or typed project names to (title, path) pairs for this machine."""
    host = socket.gethostname().split(".")[0].lower()
    table = projects()
    if not names:
        machines = sorted({m for _, _, m, _ in table if m != host})
        return [(t, p) for t, p, m, _ in table if m == host], [("Projects", m) for m in machines]
    found, elsewhere = [], []
    for name in names:
        key = name.strip().lower()
        hit = next((row for row in table if key in (row[0].lower(), row[1])
                    or key in [a.strip() for a in row[3].split(",")]), None)
        if hit is None:
            found.append((name, str(Path(name).expanduser())))
        elif hit[2] != host:
            elsewhere.append((hit[0], hit[2]))
        else:
            found.append((hit[0], hit[1]))
    return list(dict.fromkeys(found)), list(dict.fromkeys(elsewhere))


def threads_of(project):
    title, path = project
    output, error = t3("thread", "list", "--project", path, "--json")
    if error:
        return title, [], error
    # Subagent and delegated-task threads have a parent. Rook continues only top-level threads.
    rows = [t for t in json.loads(output) if not t.get("parentThreadId") and not t.get("archived")]
    return title, rows, None


def gather(names, days):
    found, elsewhere = resolve(names)
    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(threads_of, found))
    rows = [(title, t) for title, threads, _ in results for t in threads if days_old(t["updatedAt"]) <= days]
    rows.sort(key=lambda row: row[1]["updatedAt"], reverse=True)
    errors = [f"{title}: {error}" for title, _, error in results if error]
    errors += [f"{title} on {machine}: the t3 command cannot reach that machine, so use the T3 tools"
               for title, machine in elsewhere]
    if not names and not projects():
        errors.append(f"no projects table in {PROJECTS_FILE}, so name a project path")
    return rows, errors


def line(title, t):
    settled = " settled" if t.get("settled") else ""
    return (f"{title} | {age(t['updatedAt'])} | {state(t)}{settled} | {t.get('providerInstanceId')}/{t.get('model')}"
            f" | {t['threadId']} | {t.get('title', '')}")


def show(thread_id, messages):
    output, error = t3("thread", "show", thread_id, "--messages", str(messages), "--json")
    return (None, error) if error else (json.loads(output), None)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    listing = sub.add_parser("list")
    listing.add_argument("--days", type=float, default=7)
    listing.add_argument("--active", action="store_true", help="Only threads that are working now.")
    listing.add_argument("project", nargs="*")
    needs = sub.add_parser("needs")
    needs.add_argument("--days", type=float, default=3)
    peek = sub.add_parser("peek")
    peek.add_argument("--messages", type=int, default=3)
    peek.add_argument("thread", nargs="+")
    args = parser.parse_args()

    if args.command == "peek":
        with ThreadPoolExecutor(8) as pool:
            shown = list(pool.map(lambda tid: show(tid, args.messages), args.thread))
        for tid, (data, error) in zip(args.thread, shown):
            if error:
                print(f"== {tid}: {error}\n")
                continue
            t = data["thread"]
            pending = f", {t['pendingRequestCount']} question waiting" if t.get("pendingRequestCount") else ""
            print(f"== {t.get('title')} | {state(t)}{pending} | {t.get('model')} | {age(t['updatedAt'])} | {tid}")
            for message in data.get("messages", []):
                text = " ".join(message.get("text", "").split())
                print(f"[{message.get('role')}] {text[:600]}{' (cut)' if len(text) > 600 else ''}")
            print()
        return

    rows, errors = gather(getattr(args, "project", []), args.days)
    if args.command == "list":
        rows = [row for row in rows if not args.active or state(row[1]) in BUSY | {"working-on-subagents"}]
        print("\n".join(line(*row) for row in rows) or f"No threads in the last {args.days:g} days.")
    else:
        # Only an unsettled thread that stopped can need an answer. A settled one was already dealt with.
        candidates = [row for row in rows if not row[1].get("settled") and state(row[1]) not in BUSY | {"working-on-subagents"}]
        with ThreadPoolExecutor(8) as pool:
            shown = list(pool.map(lambda row: show(row[1]["threadId"], 1), candidates[:12]))
        found = 0
        for (title, t), (data, error) in zip(candidates, shown):
            if error:
                errors.append(f"{t['threadId']}: {error}")
                continue
            detail, last = data["thread"], (data.get("messages") or [{}])[-1]
            text = " ".join(last.get("text", "").split())
            if detail.get("pendingRequestCount"):
                reason = "waits for an answer in T3"
            elif detail.get("status") in ("failed", "interrupted", "cancelled"):
                reason = f"stopped: {detail['status']}"
            elif last.get("role") == "assistant":
                reason = "finished, not yet settled"
            else:
                continue
            found += 1
            print(f"{line(title, t)}\n  {reason}. Last: {text[:300]}")
        if not found:
            print(f"Nothing waits for an answer in the last {args.days:g} days.")
    for error in errors:
        print(f"note: {error}", file=sys.stderr)


if __name__ == "__main__":
    main()
