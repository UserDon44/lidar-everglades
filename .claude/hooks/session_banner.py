#!/usr/bin/env python3
"""
SessionStart banner: say which repo is actually rooted, out loud, first thing.

THE FAILURE THIS EXISTS TO PREVENT
==================================
For three sessions running, Claude Code was rooted at `lidar-portfolio`
while the work was in `lidar-kilauea`. Nothing announced it. The
consequences were invisible and compounding:

  - `lidar-kilauea/.claude/settings.json` was never loaded, so Kilauea's
    guard and number-audit hooks NEVER FIRED, in any session of that
    project.
  - The user opened the Kilauea folder in VS Code expecting that to fix
    it. It does not: a RESUMED conversation keeps its original root.
  - Three separate probes tried to determine which hooks were live and
    all three were incapable of answering, so their silence was read as
    "not wired" when the real answer was "wrong repo".

None of that was hard to detect. It was simply never stated. This hook
states it, once, at session start, where it cannot be missed.

WHY A BANNER AND NOT A CHECK THAT BLOCKS
========================================
There is no ground truth for "the repo the user meant". Only the user
knows that. So this does not guess and does not block -- it reports the
root, names the sibling repos whose hooks are therefore NOT loaded, and
lets a human notice in one second what previously took three sessions.

That is the whole design: convert a silent condition into a visible one.

IT ALSO LEAVES AN ARTIFACT
==========================
`last_session_banner.txt`, next to `last_number_audit.txt`. A hook that
runs invisibly is indistinguishable from one that is not installed --
that ambiguity is exactly what cost three sessions here. The artifact's
LOCATION is the discriminator: it appears in whichever repo is rooted.

Fails open, always exit 0. A broken banner must never stop a session.
"""
import json
import os
import sys
from pathlib import Path

HOOK_FILE = Path(__file__).resolve()
HOOK_REPO = HOOK_FILE.parent.parent.parent          # hooks/ -> .claude/ -> repo
ENV = Path(r"C:\Users\ryans\miniforge3\envs\lidar")
BACKUP_ROOT = Path(r"C:\Users\ryans\OneDrive")
SIBLING_GLOB = "lidar-*"


def head_sha(repo):
    """Current commit sha without invoking git. Returns None if unknown."""
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
            return None
        return h[:12]
    except Exception:
        return None


def main():
    try:
        json.load(sys.stdin)
    except Exception:
        pass

    lines = []
    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    root = Path(root).resolve()

    lines.append(f"SESSION ROOT: {root}")
    lines.append(f"hooks loaded from: {HOOK_REPO}")

    # The banner script and the session root should be the same repo. They
    # can differ if settings point elsewhere; say so rather than assume.
    if HOOK_REPO.resolve() != root:
        lines.append(f"  NOTE: this hook lives in {HOOK_REPO.name} but the "
                     f"session root is {root.name}")

    # Sibling repos whose hooks are therefore NOT loaded. This is the line
    # that would have surfaced the three-session failure immediately.
    try:
        sibs = sorted(p for p in root.parent.glob(SIBLING_GLOB)
                      if p.is_dir() and (p / ".claude").is_dir())
    except Exception:
        sibs = []
    if len(sibs) > 1:
        others = [p.name for p in sibs if p.resolve() != root]
        if others:
            lines.append(f"  hooks NOT loaded for: {', '.join(others)}")
            lines.append("  (settings load from the session root only; adding"
                         " a working directory does not load its settings)")

    # Environment: the conda env is not activated in this shell, and the
    # PowerShell profile that would activate it is blocked by execution
    # policy. Report resolvability rather than assuming it.
    pdal = ENV / "Library" / "bin" / "pdal.exe"
    py = ENV / "python.exe"
    lines.append(f"env: python {'ok' if py.is_file() else 'MISSING'}  "
                 f"pdal {'ok' if pdal.is_file() else 'MISSING'}  "
                 f"(explicit paths; conda is not on PATH here)")

    # Backup staleness -- the thing that silently rots between sessions.
    sha = head_sha(root)
    bk = BACKUP_ROOT / f"{root.name}-backup"
    if sha and bk.is_dir():
        bsha = head_sha(bk)
        if bsha is None:
            lines.append(f"backup: {bk.name} present, HEAD unreadable")
        elif bsha == sha:
            lines.append(f"backup: current ({sha})")
        else:
            lines.append(f"backup: STALE -- repo {sha}, backup {bsha}")
    elif sha:
        lines.append(f"backup: none found at {bk}")

    text = "\n".join(lines)

    try:
        (HOOK_FILE.parent / "last_session_banner.txt").write_text(
            text, encoding="utf-8")
    except Exception:
        pass

    print(json.dumps({
        "systemMessage": text,
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": (
                "Session root and hook-loading state:\n" + text +
                "\n\nIf the root is not the repo you intend to work in, that "
                "repo's hooks are NOT active. Opening the folder in an editor "
                "does not re-root a RESUMED conversation -- start a new one."
            ),
        },
    }))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
