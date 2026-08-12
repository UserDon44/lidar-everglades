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

WHY EVERY RULE IS BOUNDED TO ONE LINE  (decision, 2026-08-12)
------------------------------------------------------------
Every segment matcher is `[^|;&\n]*`, not `[^|;&]*`. The newline is
deliberate and was added after the FOURTH false positive of one family.

`[^|;&]` is a NEGATED class, so it matches newlines. Shell separates
commands by `|`, `;`, `&` **and newline**, so without `\n` a rule that
means "within this one command" silently ran on the entire rest of the
input -- including heredoc BODIES. Appending a document that merely
mentioned `data/raw` was blocked, because the match started at `>>` and
ran past the redirect target and `<<'EOF'` into the prose.

The root cause behind three of the four false positives is one thing:
**data inside a command string being scanned as shell.** `--porcelain`
was a flag word read as a flag; the commit message and the heredoc were
document text read as commands. Patching rule-by-rule is how a guard
becomes something people route around, which is the inert-hook failure
arriving by a slower road.

WHAT THIS PRESERVES, AND WHAT IT COSTS -- measured, not predicted
The change is NARROWER than first assumed. Three predictions about it
were wrong and the regression suite corrected them (29 cases, 0 failures,
`scratchpad/guard_v3.py`):

  keeps: flag position anywhere on the line. `git push origin main
         --force` still blocks -- the property the whole-string scan
         existed for.
  keeps: all recursive+force spellings, and every data/raw rule.
  keeps: **document text that looks like a command on ONE line.** A commit
         message saying "a bug where rm -rf was used" still blocks,
         because `rm` and `-rf` share a line and the newline bound never
         comes into play. The deliberate choice to keep blocking such
         messages therefore SURVIVES this fix -- it was predicted to be
         lost and is not.
  keeps: `rm -rf \` + newline + `  /path`. Also predicted lost, also
         wrong: the command and its flags share line 1.
  fixes: only the case where a trigger is split ACROSS the redirect
         boundary -- `>` or `>>` on line 1 and the protected path in a
         heredoc body several lines down. That was the actual false
         positive, and it is the whole of what changed.
  loses: a split that separates a command from its flags, i.e.
         `rm \` + newline + `  -rf /path`.

That single loss is accepted knowingly. The scope note below already
concedes the guard is evadable by variables, aliases and indirection, so
trading one more route that requires deliberate line-splitting for the
removal of a whole false-positive family is the better bargain. Recorded
rather than absorbed silently: a guard whose coverage quietly shrinks is
worse than one whose limits are written down.

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
        # A short flag cluster is a SINGLE dash followed by letters, hence
        # `-(?!-)[a-z]*r`; long flags must match EXACTLY. The previous
        # `-{1,2}[a-z-]*r` matched the r inside ANY long flag, so
        # `--porcelain` read as a recursive flag and blocked
        # `rm -f x && git status --porcelain`.
        #
        # The scan is also limited to rm's OWN command segment, [^|;&\n]*,
        # the way every other rule here already was -- this rule's `.*`
        # reached across && into unrelated commands, so `rm -f x && tar -r y`
        # blocked too.
        r"\brm\b"
        r"(?=[^|;&\n]*(?:\s-(?!-)[a-z]*r|\s--recursive\b))"
        r"(?=[^|;&\n]*(?:\s-(?!-)[a-z]*f|\s--force\b))",
        "rm with both recursive and force flags, in any spelling "
        "(-rf, -fr, -r -f, --recursive --force).",
    ),
    (
        r"\b(?:rm|shred|truncate|mv)\b[^|;&\n]*\bdata[/\\]raw\b",
        "a destructive command targeting data/raw. Delivered source "
        "tiles are immutable -- re-download instead of editing.",
    ),
    (
        r">\s*[^|;&\n]*\bdata[/\\]raw\b",
        "shell redirection into data/raw, which would overwrite a "
        "delivered source tile.",
    ),
    (
        # Same flag-matching fix as rm: `--profile` contains an f and was
        # read as --force. Also switched to lookaheads so the flag no
        # longer has to appear BEFORE the data/raw operand -- the old form
        # let `cp data/raw/x.laz y.laz -f` through entirely.
        r"\bcp\b"
        r"(?=[^|;&\n]*(?:\s-(?!-)[a-z]*f|\s--force\b))"
        r"(?=[^|;&\n]*\bdata[/\\]raw\b)",
        "cp -f into data/raw, which would overwrite a delivered source "
        "tile.",
    ),
    (
        r"\bgit\s+(?:checkout|restore)\b[^|;&\n]*\bdata[/\\]raw\b",
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
