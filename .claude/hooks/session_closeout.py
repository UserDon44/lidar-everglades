#!/usr/bin/env python3
"""
SessionEnd closeout check: make the closeout rule a check, not a paragraph.

THE FAILURE THIS EXISTS TO PREVENT
==================================
The project rule says: at the end of any working session, update CLAUDE.md
and append a dated entry to the session log, without being asked. It is a
good rule and it has been followed -- BY HAND, every time.

`~/.claude/CLAUDE.md` records three separate cases where a written rule was
known, believed to be in force, and broken anyway, and draws the
conclusion directly: **the rule is not the mechanism.** A paragraph
produces, at best, a correct reading; it does not produce a correct
outcome, and nothing FAILS when it is not followed.

This is the failing part. It runs at SessionEnd and reports, factually:

  - uncommitted changes still in the tree
  - whether CLAUDE.md and the session log were touched this session
  - whether the OneDrive backup is behind the repo

WHY SessionEnd AND NOT Stop
===========================
`Stop` fires at the end of EVERY assistant turn. A closeout reminder on
every turn is noise, and noise is how a check gets ignored and then
routed around -- the inert-hook failure by a slower road. SessionEnd
fires once, which is when the question is actually meaningful.

The cost of that choice, stated: SessionEnd output may arrive as the UI is
tearing down, so the artifact below is the reliable record, not the
message.

IT LEAVES AN ARTIFACT, DELIBERATELY
===================================
`last_closeout_check.txt`. Same reasoning as `last_number_audit.txt`: a
hook whose only output is a message you might not see is indistinguishable
from a hook that never ran. The file is the evidence, and its LOCATION
names the repo that was actually rooted.

Fails open, always exit 0.
"""
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HOOK_FILE = Path(__file__).resolve()
REPO = HOOK_FILE.parent.parent.parent
BACKUP_ROOT = Path(r"C:\Users\ryans\OneDrive")
WATCHED = ("CLAUDE.md", "docs/session-log.md")


def git(*args, timeout=20):
    """Run git in the repo. Returns stdout, or None on any failure.

    Timeout is passed to subprocess, which enforces it OUTSIDE the read
    loop -- the shape this project had to learn twice.
    """
    try:
        p = subprocess.run(("git", "-C", str(REPO)) + args,
                           capture_output=True, text=True, timeout=timeout)
        return p.stdout if p.returncode == 0 else None
    except Exception:
        return None


def head_sha(repo):
    try:
        g = repo / ".git"
        h = (g / "HEAD").read_text(encoding="utf-8").strip()
        if h.startswith("ref:"):
            ref = h.split(None, 1)[1].strip()
            loose = g / ref
            if loose.is_file():
                return loose.read_text(encoding="utf-8").strip()[:12]
            packed = g / "packed-refs"
            if packed.is_file():
                for line in packed.read_text(encoding="utf-8").splitlines():
                    if line.endswith(" " + ref):
                        return line.split()[0][:12]
        else:
            return h[:12]
    except Exception:
        pass
    return None


def main():
    try:
        json.load(sys.stdin)
    except Exception:
        pass

    out = [f"CLOSEOUT CHECK  {datetime.now():%Y-%m-%d %H:%M}  {REPO.name}"]
    todo = []

    status = git("status", "--porcelain")
    if status is None:
        out.append("git: unavailable -- tree state unknown")
    elif status.strip():
        n = len(status.strip().splitlines())
        out.append(f"UNCOMMITTED: {n} path(s)")
        for line in status.strip().splitlines()[:10]:
            out.append(f"    {line}")
        todo.append(f"{n} uncommitted path(s)")
    else:
        out.append("tree: clean")

    # Was the durable record actually updated? Touched in the last commit
    # OR sitting dirty both count -- the point is whether the session left
    # a trace in the files that carry memory forward.
    recent = git("log", "-1", "--name-only", "--pretty=format:") or ""
    dirty = status or ""
    for w in WATCHED:
        base = w.split("/")[-1]
        if base in recent or base in dirty:
            out.append(f"updated: {w}")
        else:
            out.append(f"NOT updated in the last commit: {w}")
            todo.append(f"{w} not updated")

    sha = head_sha(REPO)
    bk = BACKUP_ROOT / f"{REPO.name}-backup"
    if sha and bk.is_dir():
        bsha = head_sha(bk)
        if bsha == sha:
            out.append(f"backup: current ({sha})")
        else:
            out.append(f"backup: STALE -- repo {sha}, backup {bsha}")
            todo.append("backup stale")
    elif sha:
        out.append(f"backup: none at {bk}")
        todo.append("no backup")

    out.append("")
    if todo:
        out.append("OUTSTANDING: " + "; ".join(todo))
    else:
        out.append("nothing outstanding.")
    out.append("NOTE: this checks that the files CHANGED, never that the "
               "change was adequate.")

    text = "\n".join(out)
    try:
        (HOOK_FILE.parent / "last_closeout_check.txt").write_text(
            text, encoding="utf-8")
    except Exception:
        pass

    print(json.dumps({"systemMessage": text}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
