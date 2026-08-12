#!/usr/bin/env python3
"""
PostToolUse check: every number in a deliverable must trace to a saved
artifact.

WHAT THIS CHECKS, AND THE LIMITATION THAT MATTERS MOST
======================================================
THIS IS A COMPLETENESS CHECK, NOT A CORRECTNESS CHECK.

It verifies that a number appearing in a deliverable also appears
somewhere durable -- a script, a measurement dump, a pipeline JSON. It
CANNOT tell you the number is right.

Concretely: this project's predecessor published an "8.08 ft" difference
between two DEM parameter settings. That figure was computed by a real
script, saved to a real file, and completely wrong -- it had been
measured against the wrong baseline, and the two rasters it claimed to
distinguish were byte-identical. THIS HOOK WOULD HAVE PASSED IT GREEN.

Anyone reading a green result must understand that. A number can be
fully traceable and still be nonsense. The check closes exactly one
failure mode -- a number whose derivation was never saved at all, which
is the mode that has actually bitten this work repeatedly:

  - figures generated, discussed, then gone when the report was written
  - hydrology volumes that lived only in a terminal scrollback
  - a CHM cluster count published as 13 that no radius reproduces
  - an S-151 query string recorded wrong, so its coordinates could not
    be re-derived

It cannot close the mode where the derivation exists and is wrong. That
still requires reading the method.

TIERS
=====
  UNTRACED   the number appears in no artifact anywhere -> loud failure
  AMBIGUOUS  it appears, but only in a file with no recorded parameters
             (no module docstring) -> warn, name the file
  TRACED     it appears in an artifact whose script documents its
             parameters, or it is explicitly annotated in the text as
             [tool output] or [cited: source]

The annotation escape hatch is deliberate: it is the WhiteboxTools
pit-count convention -- "if a number can only come from tool console
output, attribute it explicitly" -- made machine-readable instead of
remembered.

DELIBERATELY NOT TUNED
======================
The AMBIGUOUS tier is intentionally noisy on first run. No structural
exemptions are applied -- section numbers, years, table indices and
percentages are all reported. Narrowing the matcher is a decision for
the human reading the output, not for whoever wrote the check. A check
quietly adjusted until it passes is worse than no check, because it
still looks like verification.

Full detail is written to .claude/hooks/last_number_audit.txt.

READING last_number_audit.txt: IT IS NOT PROOF THIS HOOK RAN
------------------------------------------------------------
The file is written by this script, and this script can be run by hand.
Its presence therefore means "someone executed this code at some point",
NOT "the hook fired on save". Do not read it as coverage.

That distinction is not hypothetical. From configuration until
2026-08-12 this hook NEVER EXECUTED as a hook in any project: it was
invoked as "$CLAUDE_PROJECT_DIR/.claude/hooks/x.py", relying on the
#!/usr/bin/env python3 shebang, which on this machine resolves to the
Windows Store stub -- "Python was not found", exit 49. Every deliverable
in the San Xavier and Everglades projects was written with this check
inert. The audits those projects cite were real but MANUAL: a person ran
this script deliberately. The 23x-vs-15x baseline error was caught that
way, not by a save triggering the hook.

An artifact that implies coverage it never provided is worse than no
artifact, which is why this paragraph is here rather than only in
CLAUDE.md.

To confirm the hook is actually live, do not look for this file. Edit a
file under output/reports/ containing a number and check that PostToolUse
context comes back. A number-free edit produces silence that is
indistinguishable from a dead hook -- that mistake was made three times
in a row on 2026-08-12.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

# Numbers with at least one digit, optional sign/decimal/thousands
# separators, not glued to letters (so "EPSG:6350" and "w3_s0.05" still
# yield their numbers, but "e1557n0456" is treated as an identifier).
NUM_RE = re.compile(r"(?<![\w.])[-+]?\d{1,3}(?:,\d{3})+(?:\.\d+)?(?![\w])"
                    r"|(?<![\w.])[-+]?\d+\.\d+(?![\w])"
                    r"|(?<![\w.])[-+]?\d+(?![\w.])")

ANNOTATED_RE = re.compile(r"\[tool output\]|\[cited:[^\]]*\]", re.IGNORECASE)

# CATEGORICAL exemptions -- patterns describing a KIND of non-measurement,
# never a list of specific values. A value list would become a place to
# quietly park inconvenient numbers, which is the failure this whole hook
# exists to prevent: it would look like a passing check while hiding the
# thing it was meant to catch.
#
# Matching spans are masked out BEFORE numbers are extracted, so the
# exemption is structural rather than a post-hoc filter on results.
#
# KNOWN COST, stated rather than discovered later: the year pattern will
# also mask a genuine measurement that happens to be a bare integer
# between 1900 and 2099 (e.g. a cell count of "2018"). Decimal values,
# comma-grouped values, and anything with units are unaffected. This is a
# real false-negative and is accepted deliberately in exchange for not
# maintaining a value list.
EXEMPT_PATTERNS = [
    # ISO dates and date fragments: 2026-08-11
    r"\b\d{4}-\d{2}-\d{2}\b",
    # Bare 4-digit years, incl. datum realisations like NAD83(2011)
    r"\b(?:19|20)\d{2}\b",
    # Section references: §5, §5.1, §3-3b, "sections 3-3b"
    r"§\s*\d+(?:\.\d+)*(?:\s*[-–]\s*\d*[a-z]?)?",
    r"\bsections?\s+\d+(?:\.\d+)*(?:\s*[-–]\s*\d*[a-z]?)?",
    # Markdown section headings: "### 5.1 The crown is truncated ..."
    # (a section reference that carries no section symbol)
    r"^#{1,6}\s+\d+(?:\.\d+)*",
    # Dotted version strings, optionally after a tool name: PDAL 2.10.0
    r"\b\d+\.\d+\.\d+\b",
    r"\b(?:PDAL|GDAL|Python|numpy|scipy|rasterio|laspy|pyproj)\s+v?\d+(?:\.\d+)*",
    # Authority-qualified identifiers: EPSG:6350, class 2 codes stay visible
    r"\bEPSG:\s*\d+",
]
EXEMPT_RE = re.compile("|".join(EXEMPT_PATTERNS),
                       re.IGNORECASE | re.MULTILINE)


def mask_exempt(text):
    """Blank out categorically-exempt spans so their digits never surface."""
    return EXEMPT_RE.sub(lambda m: " " * len(m.group()),
                         normalize_typography(text))

# EVIDENCE BASE -- deliberately excludes output/reports/ and docs/.
#
# The first version of this hook globbed output/**/*.md, which put the
# deliverables themselves into the evidence base. It reported 172 of 172
# numbers "traced" on qc_memo.md because the memo traced to ITSELF, and
# any two deliverables citing each other would have validated each other.
# A check that cannot fail is not a check, and it fails green -- which is
# the most dangerous direction.
#
# Evidence must be something that COMPUTES or RECORDS a number: a script,
# a pipeline definition, or a measurement dump. Prose citing prose is not
# provenance.
SEARCH_GLOBS = [
    "scripts/**/*.py",
    "scripts/pipelines/*.json",
    "output/**/*.txt",
    "output/**/*.csv",
    "output/**/*.json",
]

# The exclusion is on PROSE, not on a directory. output/reports/ holds
# both kinds of file and they play opposite roles:
#
#   *.md  deliverables -- the thing being audited. Excluded, or a memo
#         traces to itself and two memos validate each other.
#   *.txt measurement dumps written by scripts/dump.py, each carrying a
#         mandatory parameters header. These are exactly the evidence
#         the audit is looking for and MUST be included.
#
# An earlier version excluded the whole directory and therefore ignored
# the dumps that had just been created to fix the problem -- the audit
# kept reporting untraced numbers that were sitting in a file it refused
# to read.
def is_prose(rel):
    return rel.endswith(".md") or rel.startswith("docs/")

MAX_REPORT = 25


def norm(tok):
    """Canonical form so 0.0807, .0807 and 0,081 compare sensibly."""
    return tok.replace(",", "").lstrip("+").rstrip(".")


# Typographic characters that ARE arithmetic but are not ASCII. The memo
# renders negatives with U+2212 MINUS SIGN and ranges with en dashes, so
# "-0.7096" in a dump never matched "−0.710" in prose -- the sign was
# silently dropped and the number compared as positive. Normalising here
# rather than widening the number regex keeps the sign meaningful.
def normalize_typography(text):
    return (text.replace("−", "-")     # minus sign
                .replace("–", "-")     # en dash
                .replace("—", "-"))    # em dash


def as_float(tok):
    try:
        return float(norm(tok))
    except ValueError:
        return None


def decimals(tok):
    t = norm(tok)
    return len(t.split(".")[1]) if "." in t else 0


# Deliverables ROUND for presentation: the dump holds 0.0807, the memo
# prints 0.081. Verbatim matching can never reconcile those, and demanding
# full precision in prose would be a worse deliverable. So a number traces
# if ANY artifact value rounds to it at the precision the deliverable
# chose to state. This is not a loosened threshold -- it is the correct
# comparison. An artifact value of 0.9 does NOT satisfy a claim of 0.0807.
MAX_DP = 8


def gather_artifacts(root):
    """Map every number found in project artifacts -> list of files.

    A file is 'parameterised' if it opens with a module docstring, which
    is this project's convention for recording HOW a number was made.
    That is a proxy, and a loose one -- it is why the middle tier is
    called AMBIGUOUS rather than UNPARAMETERISED.
    """
    index = {}
    documented = set()
    rounded = {}
    for pattern in SEARCH_GLOBS:
        for path in root.glob(pattern):
            if not path.is_file():
                continue
            rel = str(path.relative_to(root)).replace("\\", "/")
            if is_prose(rel):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if path.suffix == ".py":
                head = text.lstrip()
                if head.startswith('"""') or head.startswith("'''"):
                    documented.add(path)
            else:
                documented.add(path)
            for m in NUM_RE.finditer(normalize_typography(text)):
                tok = m.group()
                index.setdefault(norm(tok), set()).add(path)
                f = as_float(tok)
                if f is None:
                    continue
                # Register the value at every presentation precision, so a
                # rounded quotation in prose still resolves to this source.
                for d in range(MAX_DP + 1):
                    rounded.setdefault(d, {}).setdefault(
                        f"{round(f, d):.{d}f}", set()).add(path)
    return index, documented, rounded


def changed_text(root, tool_name, tool_input):
    """The text whose numbers we audit."""
    if tool_name in ("Write", "Edit"):
        fp = tool_input.get("file_path") or ""
        p = Path(fp)
        if not p.is_absolute():
            p = root / fp
        try:
            rel = p.resolve().relative_to(root.resolve())
        except Exception:
            return None, None
        if not str(rel).replace("\\", "/").startswith("output/reports/"):
            return None, None
        # Audit only what this call introduced, where we can tell.
        if tool_name == "Edit" and tool_input.get("new_string"):
            return tool_input["new_string"], p
        try:
            return p.read_text(encoding="utf-8", errors="ignore"), p
        except Exception:
            return None, None

    if tool_name in ("Bash", "PowerShell"):
        cmd = tool_input.get("command") or ""
        if "git commit" not in cmd:
            return None, None
        try:
            out = subprocess.run(
                ["git", "diff", "HEAD~1", "--unified=0", "--", "output/reports/"],
                cwd=str(root), capture_output=True, text=True, timeout=30)
            added = "\n".join(l[1:] for l in out.stdout.splitlines()
                              if l.startswith("+") and not l.startswith("+++"))
            return added, Path("output/reports/ (committed diff)")
        except Exception:
            return None, None

    return None, None


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    root = Path(__file__).resolve().parent.parent.parent
    tool = payload.get("tool_name") or ""
    ti = payload.get("tool_input") or {}

    text, target = changed_text(root, tool, ti)
    if not text:
        return 0

    index, documented, rounded = gather_artifacts(root)

    untraced, ambiguous, traced = [], [], []
    in_cited_table = False
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("|"):
            if ANNOTATED_RE.search(raw_line):
                in_cited_table = True
                continue
            if in_cited_table:
                continue  # body of a table whose header names its source
        else:
            in_cited_table = False
        if ANNOTATED_RE.search(raw_line):
            continue  # explicitly attributed; the convention, honoured
        line = mask_exempt(raw_line)
        for m in NUM_RE.finditer(line):
            tok = m.group()
            key = norm(tok)
            where = index.get(key)
            if not where:
                f = as_float(tok)
                if f is not None:
                    d = decimals(tok)
                    where = rounded.get(d, {}).get(f"{round(f, d):.{d}f}")
            if not where:
                untraced.append((tok, raw_line.strip()[:110]))
            elif any(p in documented for p in where):
                traced.append(tok)
            else:
                ambiguous.append((tok, sorted(p.name for p in where)[:3]))

    total = len(untraced) + len(ambiguous) + len(traced)
    if total == 0:
        return 0

    log = root / ".claude" / "hooks" / "last_number_audit.txt"
    with open(log, "w", encoding="utf-8") as fh:
        fh.write(f"target: {target}\n")
        fh.write(f"traced {len(traced)} | ambiguous {len(ambiguous)} | "
                 f"untraced {len(untraced)}  (of {total})\n\n")
        fh.write("UNTRACED -- appears in no artifact:\n")
        for tok, ctx in untraced:
            fh.write(f"  {tok:<16} {ctx}\n")
        fh.write("\nAMBIGUOUS -- found only in files without recorded parameters:\n")
        for tok, files in ambiguous:
            fh.write(f"  {tok:<16} {', '.join(files)}\n")

    lines = [
        f"deliverable number audit -- {getattr(target, 'name', target)}",
        f"  traced {len(traced)} | ambiguous {len(ambiguous)} | "
        f"UNTRACED {len(untraced)}  (of {total} numbers)",
    ]
    if untraced:
        lines.append("  UNTRACED (no artifact contains these):")
        for tok, ctx in untraced[:MAX_REPORT]:
            lines.append(f"    {tok:<14} | {ctx}")
        if len(untraced) > MAX_REPORT:
            lines.append(f"    ... and {len(untraced)-MAX_REPORT} more")
        lines.append("  Fix by adding the artifact or removing the claim.")
        lines.append("  NOTE: this checks that a derivation EXISTS, never that "
                     "it is correct.")
    lines.append(f"  full detail: {log}")

    msg = "\n".join(lines)
    print(json.dumps({
        "systemMessage": msg,
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": msg,
        },
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
