#!/usr/bin/env python3
"""
PreToolUse guard for destructive shell commands.

WHY THIS EXISTS ALONGSIDE THE DENY LIST
---------------------------------------
settings.json permission rules are PREFIX matches. That is enough for
"command starts with X", but three of the things worth denying cannot be
written that way:

  git push --force   : a prefix rule catches `git push --force origin main`
                       but NOT `git push origin main --force`. The flag can
                       legally appear at any position.
  rm -rf             : -rf, -fr, -r -f, -f -r, --recursive --force are all
                       the same command with different spellings.
  data/raw damage    : `mv`, `cp -f`, `truncate`, `>` redirection and
                       `shred` can all modify a delivered source tile
                       without the word "rm" appearing at all.

This hook scans the WHOLE command string, so flag position and spelling
do not matter. It returns permissionDecision "deny", which cannot be
overridden by an allow rule.

SCOPE, STATED HONESTLY
----------------------
This is a guard against mistakes, NOT a security boundary. It reads one
command string with regexes. It does not:

  - resolve shell variables, aliases, or command substitution
    (`R=data/raw; rm -rf "$R"` is not caught)
  - follow indirection through a script that is itself invoked
    (`bash cleanup.sh` is not inspected)
  - understand quoting well enough to be un-evadable

Anyone determined to defeat it can. That is fine: the threat model is an
absent-minded destructive command during a long approve-everything
session, which is exactly the failure the allowlist is meant to reduce.
Do not treat a passing check as proof a command is safe.
"""
import json
import re
import sys

# (pattern, human explanation). Patterns are matched against the full
# command string, case-insensitively, so flag ORDER and POSITION are
# irrelevant -- which is the entire point of doing this here rather than
# in a prefix-matching deny rule.
RULES = [
    (
        r"\bgit\s+push\b(?=.*(?:\s--force\b|\s-f\b|\s--force-with-lease\b))",
        "git push with a force flag (any position). Force-push discards "
        "remote history; push normally, or rebase and open a PR.",
    ),
    (
        r"\brm\b(?=.*\s-{1,2}[a-z-]*r)(?=.*\s-{1,2}[a-z-]*f)",
        "rm with both recursive and force flags, in any spelling "
        "(-rf, -fr, -r -f, --recursive --force).",
    ),
    (
        r"\b(?:rm|shred|truncate|mv)\b[^|;&]*\bdata[/\\]raw\b",
        "a destructive command targeting data/raw. Delivered source "
        "tiles are immutable -- re-download instead of editing.",
    ),
    (
        r">\s*[^|;&]*\bdata[/\\]raw\b",
        "shell redirection into data/raw, which would overwrite a "
        "delivered source tile.",
    ),
    (
        r"\bcp\b[^|;&]*\s-{1,2}[a-z-]*f[^|;&]*\bdata[/\\]raw\b",
        "cp -f into data/raw, which would overwrite a delivered source "
        "tile.",
    ),
    (
        r"\bgit\s+(?:checkout|restore)\b[^|;&]*\bdata[/\\]raw\b",
        "git checkout/restore over data/raw. Those files are gitignored, "
        "so this cannot restore them and may destroy them.",
    ),
]


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        # A guard that crashes must not block work. Fail open, loudly.
        print(json.dumps({
            "systemMessage": "guard_destructive: could not parse hook input; "
                             "command NOT checked."
        }))
        return 0

    ti = payload.get("tool_input") or {}
    cmd = ti.get("command") or ""
    if not isinstance(cmd, str) or not cmd.strip():
        return 0

    for pattern, why in RULES:
        if re.search(pattern, cmd, re.IGNORECASE):
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        f"BLOCKED by .claude/hooks/guard_destructive.py: {why}\n"
                        f"Command: {cmd[:400]}\n"
                        "If this is genuinely intended, run it yourself in a "
                        "terminal -- the guard deliberately has no override "
                        "flag."
                    ),
                }
            }))
            return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
