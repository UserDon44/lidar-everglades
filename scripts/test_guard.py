#!/usr/bin/env python3
"""
Regression suite for .claude/hooks/guard_destructive.py.

Lives in the repo, not a scratchpad: this is the mechanical check that
the guard's stated coverage is its real coverage, and a check that only
exists in a temp directory is one that will not be run again. Same rule
as figures -- if it is meant to survive, it goes in the tree.

TWO THINGS IT DOES DELIBERATELY

1. It IMPORTS the live RULES table rather than transcribing the patterns,
   so the suite cannot silently drift from the file it is testing. It
   also asserts the rule COUNT, because a rule added without a test is
   the gap this is meant to prevent.

2. Every trigger string is assembled from fragments at runtime
   ("rm " + "-rf"). The guard scans whole command strings, so a literal
   test corpus in a file that is later `cat`ed or committed will block
   the very command that runs the tests. That has now happened five
   times in this project.

Run:  python scripts/test_guard.py
"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / ".claude" / "hooks" / "guard_destructive.py"
PY = sys.executable

RAW = "data" + "/" + "raw"
NL = "\n"
CONT = " \\" + NL + "  "          # backslash line-continuation

EXPECTED_RULE_COUNT = 6


def load_rules():
    spec = importlib.util.spec_from_file_location("guard", HOOK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.RULES


def run(cmd):
    p = subprocess.run([PY, str(HOOK)], input=json.dumps(
        {"tool_name": "Bash", "tool_input": {"command": cmd}}),
        capture_output=True, text=True)
    return bool(p.stdout.strip())


# (label, command, should_block)
CASES = [
    # ---- must block: the reasons this guard exists ----
    ("recursive+force", "rm " + "-rf foo", True),
    ("spelling -fr", "rm " + "-fr foo", True),
    ("split flags one line", "rm " + "-r " + "-f foo", True),
    ("long flags", "rm " + "--recursive --force foo", True),
    ("flag after operand", "rm " + "-R foo " + "-f", True),
    ("force flag LAST on push", "git push origin main " + "--force", True),
    ("force flag first", "git push " + "--force origin main", True),
    ("force-with-lease", "git push origin main " + "--force-with-lease", True),
    ("mv out of raw", "mv " + RAW + "/x.laz /tmp/", True),
    ("redirect into raw", "echo hi > " + RAW + "/x.laz", True),
    ("cp -f into raw", "cp " + "-f a.laz " + RAW + "/b.laz", True),
    ("cp flag last", "cp " + RAW + "/b.laz other.laz " + "-f", True),
    ("checkout over raw", "git checkout -- " + RAW + "/x.laz", True),
    ("shred raw", "shred " + RAW + "/x.laz", True),
    ("continuation, flags on line 1", "rm " + "-rf" + CONT + "/tmp/x", True),

    # ---- must NOT block: ordinary work ----
    ("plain rm", "rm " + "foo.txt", False),
    ("force only", "rm " + "-f foo.txt", False),
    ("recursive only", "rm " + "-r foo", False),
    ("--porcelain after rm -f", "rm " + "-f x && git status --porcelain a/", False),
    ("cross-command -r", "rm " + "-f x && tar -r y.tar z", False),
    ("cross-pipe -r", "rm " + "-f x | grep -r pattern", False),
    ("normal push", "git push origin main", False),
    ("list raw", "ls " + RAW, False),
    ("cp -f elsewhere", "cp " + "-f a.laz backup/b.laz", False),

    # ---- data-as-shell: document text, NOT commands ----
    ("heredoc body names raw path",
     "cat >> docs/log.md <<'EOF'" + NL + "prose about " + RAW + "/2019/" + NL + "EOF",
     False),
    ("heredoc body, single >",
     "cat > notes.txt <<'EOF'" + NL + "the " + RAW + " dir is protected" + NL + "EOF",
     False),
    ("heredoc body describes rm -rf",
     "git commit -F - <<'EOF'" + NL + "Never run rm " + "-rf on the archive." + NL + "EOF",
     False),
    ("heredoc body describes force push",
     "git commit -F - <<'EOF'" + NL + "We never git push " + "--force here." + NL + "EOF",
     False),
    ("-m message describes rm -rf",
     'git commit -m "note: rm ' + '-rf is banned in this repo"', False),
    ("-m message describes force push",
     'git commit -m "do not git push ' + '--force on main"', False),

    # ---- accepted losses, asserted so they stay visible ----
    ("LOSS: command split from flags", "rm" + CONT + "-rf /tmp/x", False),
    ("LOSS: command split from target",
     "mv" + CONT + RAW + "/x.laz /tmp/y", False),
    ("LOSS: redirect split from target",
     "cat foo >" + CONT + RAW + "/x.laz", False),

    # ---- residual hole in heredoc stripping, asserted knowingly ----
    ("HOLE: heredoc piped to an interpreter",
     "bash <<'EOF'" + NL + "rm " + "-rf /tmp/x" + NL + "EOF", False),
]


def main():
    rules = load_rules()
    print(f"live rule table: {len(rules)} rules "
          f"(expected {EXPECTED_RULE_COUNT})")
    if len(rules) != EXPECTED_RULE_COUNT:
        print("  *** RULE COUNT CHANGED -- add cases for the new rule, "
              "then update EXPECTED_RULE_COUNT ***")
    print()
    width = max(len(c[0]) for c in CASES)
    fails = []
    for label, cmd, want in CASES:
        got = run(cmd)
        ok = got == want
        if not ok:
            fails.append(label)
        print(f"  {label:<{width}}  want {'BLOCK' if want else 'allow':<5}"
              f"  got {'BLOCK' if got else 'allow':<5}"
              f"  {'ok' if ok else '*** FAIL ***'}")
    print()
    print(f"{len(CASES)} cases, {len(fails)} failures")
    for f in fails:
        print(f"  FAILED: {f}")
    return 1 if (fails or len(rules) != EXPECTED_RULE_COUNT) else 0


if __name__ == "__main__":
    sys.exit(main())
