#!/usr/bin/env python3
"""Fully detach a long-running command from the calling session.

Double-fork + setsid: the intermediate parent exits immediately (so callers
see instant return), and the grandchild is reparented to launchd in its own
session — immune to process-group cleanup by whatever invoked it.

Usage:
    python scripts/detached_run.py <command> [args...]
"""
import os
import sys


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("usage: detached_run.py <command> [args...]")
    if os.fork() > 0:
        sys.exit(0)          # parent returns at once
    os.setsid()              # new session: shed the caller's process group
    if os.fork() > 0:
        sys.exit(0)          # intermediate parent exits; grandchild is orphaned
    with open(os.devnull, "rb") as devnull_r, open(os.devnull, "ab") as devnull_w:
        os.dup2(devnull_r.fileno(), 0)
        os.dup2(devnull_w.fileno(), 1)
        os.dup2(devnull_w.fileno(), 2)
    os.execvp(sys.argv[1], sys.argv[1:])
    sys.exit(127)            # execvp only returns on failure


if __name__ == "__main__":
    main()
