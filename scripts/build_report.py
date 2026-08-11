#!/usr/bin/env python3
"""
Assemble output/reports/qc_memo.md + output/figures/*.png into a single
PDF deliverable: output/reports/qc_report.pdf.

qc_memo.md stays the single source of truth for text -- this script parses
its markdown subset (headers, **bold**, `code`, tables, numbered/bulleted
lists) into reportlab flowables rather than duplicating the memo's content
here. Figures are inserted at the end of whichever section first mentions
them by name (FIGURE_MAP below), in reading order.
"""
import re
from pathlib import Path
from PIL import Image as PILImage
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image,
    PageBreak, HRFlowable, KeepTogether, CondPageBreak,
)

# Project root, resolved from this file's own location so these scripts
# run from any checkout rather than one hardcoded directory.
ROOT = Path(__file__).resolve().parent.parent
MEMO = ROOT / "output" / "reports" / "qc_memo.md"
FIG_DIR = ROOT / "output" / "figures"
OUT = ROOT / "output" / "reports" / "qc_report.pdf"
APPENDIX_MD = ROOT / "output" / "reports" / "parameter_derivation.md"

PAGE_W, PAGE_H = letter
MAX_IMG_W = PAGE_W - 1.6 * inch
DPI_SOURCE = 300  # matches DPI in scripts/render_figures.py

# section heading (as it appears after "## " or "### ", stripped) -> figures
# to place at the end of that section, each (filename, caption).
FIGURE_MAP = {
    "2. Why this site": [
        ("fig06_final_surface.png",
         "Figure 1. The delivered bare-earth surface, 3 m. Hillshade uses "
         "20× vertical exaggeration because relief is 2.81 m across "
         "1 km and is invisible at 1×. The diagonal is the L-67A "
         "levee; the canal crosses it at S-151."),
    ],
    "3. Coverage is the binding constraint": [
        ("fig01_coverage.png",
         "Figure 2. All returns, ground returns, and the two void classes. "
         "Density is high (16.89 pts/m²) while ground coverage is not "
         "(1.26 pts/m²). The density banding in panel 1 is the two "
         "flight lines (§7.5); the bright feature in panel 2 is the "
         "S-151 works."),
    ],
    "4. Cell size, derived from coverage": [
        ("fig02_cell_sweep.png",
         "Figure 3. Cell-size sweep. Cells lacking a ground return fall "
         "steeply with cell size; cells lacking any return barely move, "
         "because open water returns nothing at any resolution. The gap "
         "between the curves is what larger cells recover."),
    ],
    "6. Agreement with the vendor surface": [
        ("fig05_qc_regions.png",
         "Figure 4. Difference from the vendor ground surface, and the "
         "three populations it contains. The marsh distribution (0.081 m "
         "RMSE) is the meaningful one; the pooled statistic describes none "
         "of the three."),
    ],
    "7.1 The L-67A crown is truncated by ~0.76 m — accepted and documented": [
        ("fig03_embankment_profile.png",
         "Figure 5. Embankment width against height above marsh. A levee "
         "is a wedge, and morphological opening acts on the width at the "
         "height being cut — so the 6–8.5 m crown governs, not "
         "the 32–46 m base. Vertical lines mark the span of SMRF's "
         "structuring element at cell = 3 m."),
        ("fig04_window_sweep.png",
         "Figure 6. Crest height retained against `window`, referenced to "
         "the same 706 crest cells measured in the vendor surface. No "
         "setting preserves the crown; `window` = 25 m and 50 m produce "
         "byte-identical rasters, confirming convergence. The first "
         "derivation predicted survival below 12 m and was refuted — "
         "see the Appendix."),
    ],
}

# All six figures are placed in the body via FIGURE_MAP; the appendix
# carries the derivation text, not additional plates.
APPENDIX_FIGURES = []


def _code_span(m):
    # slightly smaller than body text -- Courier glyphs run wide, and at
    # body size a long file path (e.g. output/contours/contours_2ft_
    # w120_s0.15_t1.6.gpkg) didn't fit a table column, so reportlab
    # force-split it at an arbitrary character instead of a path
    # boundary. (Tried inserting a U+200B zero-width space after each
    # "/" as a legal break point -- reportlab's base-14 Courier has no
    # glyph for it and rendered a visible tofu box, worse than the
    # original bug. Reverted; the smaller font alone gives enough margin
    # for every path in this memo to fit on one line, checked directly.)
    content = m.group(1)
    return f'<font face="Courier" size="7.6">{content}</font>'


def inline_markdown(text):
    text = text.replace("&", "&amp;")
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<i>\1</i>", text)
    text = re.sub(r"`(.+?)`", _code_span, text)
    return text


CACHE_DIR = FIG_DIR / "_pdf_cache"
CACHE_DIR.mkdir(exist_ok=True)
TARGET_DPI = 170  # print-quality on the page, but source PNGs are rendered
                   # at 300 DPI for full-resolution portfolio use elsewhere --
                   # re-encoding down to this cuts the PDF from ~95MB to a
                   # shareable size without visibly softening line art/text


def make_image(fname, max_w=MAX_IMG_W, max_h=8.8 * inch):
    path = FIG_DIR / fname
    cached = CACHE_DIR / fname
    with PILImage.open(path) as im:
        w, h = im.size
        display_w_in = min(max_w / inch, w / DPI_SOURCE)
        target_w_px = int(display_w_in * TARGET_DPI)
        if target_w_px < w:
            im = im.resize((target_w_px, int(h * target_w_px / w)), PILImage.LANCZOS)
            im.save(cached, optimize=True)
            w, h = im.size
        else:
            cached = path
    scale = min(max_w / w, max_h / h)
    return Image(str(cached), width=w * scale, height=h * scale, hAlign="CENTER")


def build_styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("MemoTitle", parent=ss["Title"], fontSize=18, spaceAfter=10))
    ss.add(ParagraphStyle("H1", parent=ss["Heading1"], fontSize=15, spaceBefore=4, spaceAfter=8,
                           textColor=colors.HexColor("#1a1a1a")))
    ss.add(ParagraphStyle("H2", parent=ss["Heading2"], fontSize=12.5, spaceBefore=10, spaceAfter=6,
                           textColor=colors.HexColor("#2a2a2a")))
    ss.add(ParagraphStyle("Body", parent=ss["BodyText"], fontSize=9.7, leading=13.5, spaceAfter=6,
                           alignment=4))  # justified
    ss.add(ParagraphStyle("ListItem", parent=ss["BodyText"], fontSize=9.7, leading=13.5,
                           spaceAfter=4, leftIndent=14, firstLineIndent=-14))
    ss.add(ParagraphStyle("Meta", parent=ss["BodyText"], fontSize=9.3, leading=13, spaceAfter=3))
    ss.add(ParagraphStyle("Caption", parent=ss["BodyText"], fontSize=8.5, leading=11,
                           alignment=TA_CENTER, textColor=colors.HexColor("#333333"),
                           spaceBefore=4, spaceAfter=14))
    return ss


PIPE_PLACEHOLDER = "\x00PIPE\x00"


def split_row(r):
    protected = r.strip().replace("\\|", PIPE_PLACEHOLDER).strip("|")
    return [c.strip().replace(PIPE_PLACEHOLDER, "|") for c in protected.split("|")]


def parse_table(rows):
    data = [split_row(r) for r in rows]
    header, _, *body = data
    data = [header] + body
    ncols = len(header)
    col_w = (PAGE_W - 1.6 * inch) / ncols
    ss = getSampleStyleSheet()
    cell_style = ParagraphStyle("cell", parent=ss["BodyText"], fontSize=8.7, leading=11)
    hdr_style = ParagraphStyle("cellhdr", parent=cell_style, fontName="Helvetica-Bold")
    tbl_data = [[Paragraph(inline_markdown(c), hdr_style) for c in header]]
    for row in body:
        tbl_data.append([Paragraph(inline_markdown(c), cell_style) for c in row])
    t = Table(tbl_data, colWidths=[col_w] * ncols, hAlign="LEFT", repeatRows=1)
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#999999")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8e8e8")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def flush_section(story, sec_key, buf):
    story.extend(buf)
    for fname, caption in FIGURE_MAP.get(sec_key, []):
        story.append(Spacer(1, 6))
        story.append(make_image(fname))
        story.append(Paragraph(caption, styles["Caption"]))


def title_page(story, meta_lines, exec_summary_text=None):
    story.append(Spacer(1, 1.1 * inch))
    story.append(Paragraph("LiDAR Bare-Earth DEM", styles["MemoTitle"]))
    story.append(Paragraph("Quality Control Memorandum", styles["MemoTitle"]))
    story.append(Spacer(1, 0.35 * inch))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#888888")))
    story.append(Spacer(1, 0.22 * inch))
    for line in meta_lines:
        story.append(Paragraph(inline_markdown(line), styles["Meta"]))
    if exec_summary_text:
        # lives on page 1, after the header block and before §1 -- someone
        # spending 90 seconds with this needs the verdict without flipping
        # pages, so this is real title-page content, not just the next
        # section in the normal flowing pipeline
        story.append(Spacer(1, 0.3 * inch))
        story.append(HRFlowable(width="100%", color=colors.HexColor("#888888")))
        story.append(Spacer(1, 0.18 * inch))
        story.append(Paragraph("EXECUTIVE SUMMARY", styles["H2"]))
        paras = ([exec_summary_text] if isinstance(exec_summary_text, str)
                 else exec_summary_text)
        for para in paras:
            story.append(Paragraph(inline_markdown(para), styles["Body"]))
    story.append(Spacer(1, 0.45 * inch))
    # This strapline is claim-bearing and must match what the project
    # actually did. Project one's version cited "the project's own signed
    # accuracy assessment" -- there is no such document for this site, and
    # no external control of any kind, which the memo is careful to state
    # in §1. Shipping the inherited wording would have put an unearned
    # credential on page 1 of a deliverable whose central discipline is
    # not claiming more than was measured.
    story.append(Paragraph(
        "Portfolio deliverable — bare-earth DEM processed from raw returns "
        "and compared against the vendor's delivered ground classification. "
        "Agreement, not accuracy: no external vertical control exists on "
        "this tile.",
        ParagraphStyle("sub", parent=styles["Body"], alignment=TA_CENTER,
                        textColor=colors.HexColor("#555555"))))
    story.append(PageBreak())


styles = build_styles()


NUMBERED_RE = re.compile(r"^\d+\.\s+")
META_LABEL_RE = re.compile(r"^\*\*[^*]+:\*\*")


def split_blocks(lines):
    """Group lines into blank-line-separated blocks, each a list of
    stripped, non-empty physical lines (markdown soft-wraps within a
    block and must be rejoined by the caller, not treated as separate
    paragraphs/list items)."""
    blocks, cur = [], []
    for line in lines:
        s = line.strip()
        if not s:
            if cur:
                blocks.append(cur)
                cur = []
        else:
            cur.append(s)
    if cur:
        blocks.append(cur)
    return blocks


def split_items(block_lines, marker_re, strip_marker=None):
    """Split a list/meta block into items, where a line matching
    marker_re starts a new item and any other line is a continuation of
    the previous item (joined with a space) -- this is what correctly
    handles markdown's soft-wrapped list items and bold-label metadata
    lines."""
    items = []
    for line in block_lines:
        if marker_re.match(line):
            text = marker_re.sub("", line, count=1) if strip_marker else line
            items.append(text)
        elif items:
            items[-1] = items[-1] + " " + line
        else:
            items.append(line)
    return items


def extract_front_matter_section(blocks, heading_text):
    """Pull a '## <heading_text>' section (its heading block + the body
    block immediately after it) out of the block list entirely, returning
    the joined body text and the blocks list with those two blocks
    removed. Used for the executive summary, which belongs on the title
    page (page 1) rendered directly by title_page(), not in the normal
    flowing section pipeline where it would land on page 2 regardless of
    how much room page 1 has left.

    Returns a LIST of paragraph strings. The original returned only the
    single block after the heading, so a multi-paragraph summary lost
    everything past the first paragraph -- and worse, the orphaned blocks
    were then picked up as meta lines and rendered ABOVE the heading.
    Consumes every block until the next heading instead."""
    for i, b in enumerate(blocks):
        if b[0].strip() == f"## {heading_text}":
            body, j = [], i + 1
            while j < len(blocks) and not blocks[j][0].lstrip().startswith("#"):
                body.append(" ".join(blocks[j]))
                j += 1
            return body, blocks[:i] + blocks[j:]
    return None, blocks


def main():
    lines = MEMO.read_text(encoding="utf-8").splitlines()
    # The full parameter derivation ships as an appendix rather than being
    # summarised twice. It carries the retracted `window` attempt, which
    # belongs in the record: the main body states the conclusion, the
    # appendix shows how it was reached and where it first went wrong.
    if APPENDIX_MD.exists():
        lines += ["", "---", "",
                  "## Appendix A. Parameter derivation in full", ""]
        for ln in APPENDIX_MD.read_text(encoding="utf-8").splitlines():
            if ln.startswith("# "):          # demote the appendix title
                continue
            if ln.startswith("## "):
                ln = "### " + ln[3:]
            elif ln.startswith("### "):
                ln = "#### " + ln[4:]
            lines.append(ln)
    blocks = split_blocks(lines)
    exec_summary_text, blocks = extract_front_matter_section(blocks, "Executive Summary")

    story = []
    meta_lines = []
    buf = []
    cur_key = None
    started = False
    in_meta = True
    pending_heading = None  # [heading Paragraph] waiting to be glued via
                             # KeepTogether to whatever content follows it,
                             # so a heading can never render alone at the
                             # bottom of a page -- a CondPageBreak alone
                             # only reserves room for the heading itself,
                             # not for the text that has to follow it, so
                             # the heading and the next few lines could
                             # still land on opposite pages

    def push(flowables):
        # append content to buf, gluing it to a just-emitted heading (if
        # any) so heading + first content block move together as one unit
        nonlocal pending_heading
        if pending_heading is not None:
            buf.append(KeepTogether(pending_heading + flowables))
            pending_heading = None
        else:
            buf.extend(flowables)

    def end_heading_block(new_top_level):
        # flush whatever section/subsection is currently open, including
        # its mapped figures, before starting the next heading. Sections
        # flow continuously (no forced page break per heading -- that
        # wasted half-empty pages); a rule + generous spacing marks each
        # new top-level section instead, and reportlab breaks naturally
        # wherever content actually runs out of room.
        nonlocal buf, cur_key, started, pending_heading
        if pending_heading is not None:
            # previous heading had no body content at all (edge case) --
            # emit it alone rather than lose it
            buf.append(KeepTogether(pending_heading))
            pending_heading = None
        if cur_key is None:
            if not started:
                title_page(story, meta_lines, exec_summary_text)
                started = True
            return
        flush_section(story, cur_key, buf)
        if new_top_level:
            story.append(Spacer(1, 10))
            story.append(HRFlowable(width="100%", thickness=0.6,
                                     color=colors.HexColor("#bbbbbb")))
        buf = []

    for block in blocks:
        first = block[0]

        if first.startswith("|"):
            # the table's own Spacer+Table+Spacer must stay one atomic
            # KeepTogether unit regardless of whether push() also glues
            # it to a preceding heading -- otherwise (the common case,
            # no heading immediately above) push() just extends buf with
            # three loose flowables and reportlab is free to split the
            # table across a page boundary again, header stranded from
            # its data despite repeatRows=1 fixing only the *reprinted*
            # header, not the split itself
            push([KeepTogether([Spacer(1, 4), parse_table(block), Spacer(1, 6)])])
            continue

        if first == "---":
            continue

        if first.startswith("# "):
            in_meta = True
            continue

        if first.startswith("## "):
            end_heading_block(new_top_level=True)
            cur_key = first[3:].strip()
            pending_heading = [CondPageBreak(1.3 * inch),
                                Paragraph(inline_markdown(cur_key), styles["H1"])]
            in_meta = False
            # remainder of this block (rare: text on the same block as
            # the heading) falls through as a paragraph below
            block = block[1:]
            if not block:
                continue
            first = block[0]

        elif first.startswith("### "):
            end_heading_block(new_top_level=False)
            cur_key = first[4:].strip()
            pending_heading = [CondPageBreak(1.0 * inch),
                                Paragraph(inline_markdown(cur_key), styles["H2"])]
            block = block[1:]
            if not block:
                continue
            first = block[0]

        if NUMBERED_RE.match(first):
            items = split_items(block, NUMBERED_RE, strip_marker=True)
            push([Paragraph(f"{n}.&nbsp;&nbsp;{inline_markdown(t)}", styles["ListItem"])
                  for n, t in enumerate(items, start=1)])
            continue

        if first.startswith("- "):
            items = split_items(block, re.compile(r"^-\s+"), strip_marker=True)
            push([Paragraph(f"•&nbsp;&nbsp;{inline_markdown(t)}", styles["ListItem"])
                  for t in items])
            continue

        if in_meta:
            items = split_items(block, META_LABEL_RE)
            meta_lines.extend(items)
            continue

        # plain paragraph: rejoin soft-wrapped lines into one string
        push([Paragraph(inline_markdown(" ".join(block)), styles["Body"])])

    if pending_heading is not None:  # heading with no body at all (edge case)
        buf.append(KeepTogether(pending_heading))
    if cur_key is not None:
        flush_section(story, cur_key, buf)

    # The appendix TEXT (the full parameter derivation) is appended to
    # the markdown in main() and flows through the normal parser, so
    # nothing is emitted here. Project one used this slot for two
    # supporting hillshades; this project has no appendix plates.
    # Side by side, not one full page each -- these are corroborating
    # evidence for a point already made in §4, not primary figures,
    # so they don't need primary-figure-sized real estate.
    # This project places all six figures in the body, so APPENDIX_FIGURES
    # is empty. The pairing layout below assumed exactly two plates and
    # index-errored on none, so it is now guarded.
    if APPENDIX_FIGURES:
        half_w = (MAX_IMG_W - 0.3 * inch) / 2
        col1, col2 = [], []
        for fname, caption in APPENDIX_FIGURES:
            col1.append(make_image(fname, max_w=half_w, max_h=6.5 * inch))
            col2.append(Paragraph(caption, styles["Caption"]))
        story.append(Spacer(1, 6))
        if len(col1) >= 2:
            row = Table([[col1[0], col1[1]]],
                        colWidths=[half_w + 0.15 * inch] * 2)
            row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
            cap_row = Table([[col2[0], col2[1]]],
                            colWidths=[half_w + 0.15 * inch] * 2)
            story.append(row)
            story.append(cap_row)
        else:
            story.append(col1[0])
            story.append(col2[0])

    doc = SimpleDocTemplate(
        str(OUT), pagesize=letter,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
        topMargin=0.75 * inch, bottomMargin=0.75 * inch,
        title="LiDAR Bare-Earth DEM — QC Memorandum",
        author="LiDAR Processing Portfolio",
    )
    doc.build(story)
    print(f"Wrote {OUT}")
    print(f"Page count: {doc.page}")


if __name__ == "__main__":
    main()
