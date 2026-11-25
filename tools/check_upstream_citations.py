#!/usr/bin/env python3
# Copyright (C) 2026 The HDF Group.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Keep `src/H5xxx.c:<line>` citations pointing at the statement they were written for.

This repository cites the libhdf5 tree constantly -- 1468 occurrences over 652
distinct file/line pairs, across registry records, fixture expectations, pickles
and generators -- and those citations rot in a way nothing can see: upstream
inserts a line, every number below it shifts, and the citation stays
syntactically perfect while pointing somewhere else.

WHAT MAKES THAT CHECKABLE is a recorded anchor.  The sibling gate
tools/check_source_citations.py requires an anchor written INLINE, in
parentheses after the citation.  That convention does not scale to 1468 sites,
and inferring an anchor from the surrounding prose was built and measured before
this file was written: of 842 citation occurrences, 425 name no function at all
in their context, and the mismatches were dominated by sentences carrying two
citations and two function names, which cross-match into false positives.

So the anchor here is neither written by hand nor inferred.  It is RECORDED, in
registry/upstream-citations.json, by `--refresh`: for each distinct citation,
the exact text of the cited line and the name of the function containing it.
Prose keeps its present spelling -- `H5HLcache.c:258`, no churn across 190 files
-- and the anchor cannot be forgotten the way an inline one can, because the
generator writes it.

WHAT THE ANCHOR BUYS, measured over the 125 upstream commits between develop
`b7b85e7abf9` and `b32cc3c776f` (about three months), replaying all 1468
occurrences across that gap:

    1149  the cited line did not move
     236  moved; the recorded text relocates UNIQUELY inside the recorded
          function -- a pure line shift, repairable with no judgement
       3  moved; the recorded text occurs twice inside the recorded function
       8  the recorded text now sits in a DIFFERENT function
      42  the recorded text is gone -- upstream edited the statement itself

The first column is the point.  Of the 289 citations that moved, 239 moved for
no reason a reader cares about, and `--fix` renumbers them in one pass.  The
remaining 50 are exactly the cases where upstream changed the code the citing
prose describes, and a human has to re-read the claim.

THE GATE THIS REPLACES caught 2 of those 50.  Its rule -- the line must hold
something other than whitespace, a lone brace or a comment delimiter -- fires
only when drift happens to land on a blank line.  Measured on the same 125
commits: 2 of the 42 genuinely-changed citations landed somewhere it could see,
and the other 40 slid onto an unrelated live statement, which is syntactically
perfect and therefore silent.  That rule survives here, but only for citations
with no recorded anchor (see `--paths` below).

ERRORS, one tag each:

    UPSTREAM_UNKNOWN_FILE       no such file in the upstream tree
    UPSTREAM_OUT_OF_RANGE       line past the end of the file
    UPSTREAM_CITATION_DRIFTED   anchor relocated; `--fix` repairs it
    UPSTREAM_CITATION_MOVED     anchor text is now in another function
    UPSTREAM_CITATION_STALE     anchor text is gone from the file
    UPSTREAM_UNANCHORED         cited in the tracked tree, absent from the index
    UPSTREAM_ORPHAN_ANCHOR      indexed, but nothing cites it any more
    UPSTREAM_NOT_A_STATEMENT    unanchored citation of a blank line or bare brace
    UPSTREAM_REANCHOR_UNUSED    `--reanchor` named a citation nobody makes

WHY `--refresh` DOES NOT REGENERATE.  The obvious spelling of the writer -- read
every citation, record what is there now -- is a trap, and a quiet one: run it
after upstream moves and it re-anchors every drifted citation to whatever
statement happens to sit at that line, which is the exact error this gate exists
to catch, performed automatically and committed as evidence.  So `--refresh`
anchors only citations that have none, drops entries nothing cites, and leaves
every standing anchor alone.  `--fix` carries a shifted anchor to its new line
rather than re-reading it there.  Re-recording in place is `--reanchor`, named
one citation at a time, for when upstream edited the statement, the line number
is still right, and a reader has confirmed the claim.  A reader who instead
corrects the NUMBER needs nothing: the key changes, the old entry is dropped as
an orphan, and the new one anchors like any other new citation.

WHAT THE BOOTSTRAP DOES NOT PROVE.  The first `--refresh` recorded whatever the
tracked citations pointed at on the day it ran.  The anchors inherit that day's
correctness; they do not establish it.  What they establish is everything after
-- that no citation changes meaning without someone saying so.

WHAT IS STILL INVISIBLE: a CONTINUATION number, which names no file and so is
not a citation to this regex.  `H5Ocopy_ref.c:193,362` (23 places) and a
backticked `:1896` after a full citation (17 places) each carry a second line
number that is never anchored, checked or renumbered.  Resolving one means
inferring which preceding file a bare `:382` belongs to, which is the same
inference that was measured and rejected for anchors.  Write a second full
citation when the number matters.

WHY IT CAN SKIP.  The upstream tree is not in this repository and its location
is a per-machine path, which portable provenance forbids recording.  So the tree
comes from $HDF5_SOURCE_DIR (the variable .devcontainer/build-hdf5.sh already
uses) and the content comparison reports itself SKIPPED when that is unset or
does not look like an HDF5 checkout.  A skip is not a pass and says so.

A SKIP IS NO LONGER TOTAL, which is the other thing the index buys.  Without any
upstream tree the checker still verifies that every citation in the tracked set
has an index entry and that the index holds nothing stale, so a citation added
without anchoring fails on a machine that has no checkout at all.  Only the
comparison against real source needs the tree.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
INDEX_REL = "registry/upstream-citations.json"
INDEX_PATH = ROOT / INDEX_REL


def set_root(path):
    """Point the whole run at another citing tree.

    Only --root uses this, and only the gate's own test passes --root: `--fix`
    rewrites tracked files in place, so it is untestable against the real tree,
    and an untested repair tool is one nobody dares run.
    """
    global ROOT, INDEX_PATH
    ROOT = Path(path).resolve()
    INDEX_PATH = ROOT / INDEX_REL

# `src/H5Dchunk.c:733`, `H5Olayout.c:123-124`, `H5Fprivate.h:412`.  The `src/`
# prefix is optional because both spellings are in use; the line range is
# optional and only its first number is anchored (the last line of a range is
# routinely a closing brace).
#
# ONE directory segment is allowed before the file name, because the VFDs that
# live in their own subdirectory -- `src/H5FDsubfiling/H5FDsubfiling.c`,
# `src/H5FDonion/...`, `src/H5FDsplitter/...` -- are cited like any other
# upstream file, and without this they matched as the bare `H5FDsubfiling.c`
# and were reported as a file that does not exist.
#
# HEADERS are matched too.  Measured when they were added: 22 distinct `.h`
# citations in 35 places, every one of them already correct -- they had simply
# never been checked.
CITATION = re.compile(
    r"\b(?:src/)?(?P<file>(?:[A-Za-z0-9_]+/)?H5[A-Za-z0-9_]*\.[ch])"
    r":(?P<lo>\d+)(?:-(?P<hi>\d+))?")

# A line that carries no statement.  A citation landing here is drift: nobody
# points a reader at a blank line or at the `*/` that ends a comment banner.
# This is the fallback gate for an unanchored citation, and the refusal rule
# for `--refresh`: an anchor recorded from one of these lines would anchor
# nothing, because the same text occurs on hundreds of other lines.
EMPTY_LINE = {"", "{", "}", "};", "*/", "/*", "} /* end for */", "} /* end if */",
              "} /* end else */", "} /* end while */"}

# HDF5 is clang-formatted with the return type on its own line and the function
# name at column 0, so the function containing a line is an upward scan for this
# with no trailing semicolon (which would make it a prototype).  Measured: it
# resolved 1438 of the 1468 citation occurrences; the other 30 are file-scope
# (macros, static tables, header declarations) and fall back to a text-only
# relocation, which is the weaker but still useful half.
FUNC_DEF = re.compile(r"^(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\(")
NOT_A_FUNCTION = {"if", "for", "while", "switch", "return", "sizeof", "do",
                  "else", "case"}

# This file states the convention, so it quotes citations that point nowhere.
#
# THE INDEX IS EXCLUDED FROM ITS OWN SCAN, which is not an optimisation.  Its
# keys are spelled exactly like citations -- `H5HLcache.c:258` -- so a tracked
# index cites every citation it records: the occurrence count doubles, every
# anchor becomes self-referential, and `--fix` renumbers the KEYS while leaving
# the text they were recorded from alone, which silently rebinds each anchor to
# a line it never described.  Measured when this was found: a full-scale `--fix`
# in a throwaway clone rewrote 329 citations in 73 files, of which the index was
# one, and left 5 citations it had just repaired still reported as drifted.
ALLOWED = {"tools/check_upstream_citations.py", INDEX_REL}


# ---- upstream tree ----------------------------------------------------------

def upstream_tree(explicit=None):
    """The libhdf5 checkout to check against, or None with a reason."""
    raw = (explicit or os.environ.get("HDF5_SOURCE_DIR", "")).strip()
    if not raw:
        return None, "HDF5_SOURCE_DIR is unset"
    tree = Path(raw).expanduser()
    if not (tree / "src" / "H5public.h").is_file():
        return None, f"{raw} does not look like an HDF5 checkout (no src/H5public.h)"
    return tree, None


def upstream_revision(tree):
    """A short revision for the OK line, or a version string when not a checkout."""
    try:
        done = subprocess.run(["git", "-C", str(tree), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True)
        if done.returncode == 0 and done.stdout.strip():
            return done.stdout.strip()
    except OSError:
        pass
    try:
        text = (tree / "src" / "H5public.h").read_text()
        nums = [re.search(rf"#define {k}\s+(\d+)", text)
                for k in ("H5_VERS_MAJOR", "H5_VERS_MINOR", "H5_VERS_RELEASE")]
        if all(nums):
            return ".".join(n.group(1) for n in nums)
    except OSError:
        pass
    return "unknown revision"


class Upstream:
    """Cached line bodies from one upstream checkout."""

    def __init__(self, tree):
        self.tree = tree
        self._cache: dict[str, list[str] | None] = {}

    def body(self, name):
        if name not in self._cache:
            path = self.tree / "src" / name
            self._cache[name] = (path.read_text(errors="replace").splitlines()
                                 if path.is_file() else None)
        return self._cache[name]


# ---- enclosing function -----------------------------------------------------

def enclosing_function(lines, lineno):
    """Name of the function containing 1-based `lineno`, or None at file scope."""
    for i in range(min(lineno, len(lines)) - 1, -1, -1):
        line = lines[i]
        m = FUNC_DEF.match(line)
        if m and m.group("name") not in NOT_A_FUNCTION and not line.rstrip().endswith(";"):
            return m.group("name")
    return None


def function_span(lines, name):
    """(start, end) of the definition of `name`, or None -- for the error message.

    The end is the first column-0 `}` after the definition, which is what
    clang-format produces for every function in this tree.
    """
    for i, line in enumerate(lines):
        m = FUNC_DEF.match(line)
        if m and m.group("name") == name and not line.rstrip().endswith(";"):
            for j in range(i, len(lines)):
                if lines[j].rstrip() == "}":
                    return i + 1, j + 1
            return i + 1, len(lines)
    return None


# ---- the index --------------------------------------------------------------

def load_index():
    """The recorded anchors, or an empty index when the file is absent."""
    if not INDEX_PATH.is_file():
        return {"schema": 1, "verified_at": None, "anchors": {}}
    try:
        doc = json.loads(INDEX_PATH.read_text())
    except (OSError, ValueError) as exc:
        sys.exit(f"{INDEX_REL}: unreadable ({exc}); regenerate with --refresh")
    doc.setdefault("anchors", {})
    return doc


def write_index(anchors, revision):
    doc = {
        "schema": 1,
        "generated_by": "tools/check_upstream_citations.py --refresh",
        "note": ("Recorded anchors for every libhdf5 line citation in the tracked "
                 "tree: the exact text of the cited line and the function "
                 "containing it, as observed in the upstream revision named by "
                 "verified_at. Generated -- do not hand-edit."),
        "verified_at": revision,
        "anchors": {k: anchors[k] for k in sorted(anchors, key=sort_key)},
    }
    INDEX_PATH.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")


def sort_key(key):
    name, _, line = key.rpartition(":")
    return (name, int(line))


def anchor_key(name, line):
    return f"{name}:{line}"


# ---- scanning the citing tree -----------------------------------------------

def tracked_files():
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files"],
                         capture_output=True, text=True)
    if out.returncode != 0:
        return None
    return [p for p in out.stdout.splitlines() if p]


def is_text(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            return b"\0" not in f.read(8192)
    except OSError:
        return False


def read_citing(rel):
    """(text, citations) for one citing file, or None when it cites nothing."""
    path = Path(rel)
    if not path.is_absolute():
        path = ROOT / rel
    if not path.is_file() or not is_text(path):
        return None
    try:
        text = path.read_text()
    except (OSError, UnicodeDecodeError):
        return None
    if ".c:" not in text and ".h:" not in text:
        return None
    cites = list(CITATION.finditer(text))
    return (text, cites) if cites else None


def scan(files):
    """Yield (rel, text, match) for every citation in `files`."""
    for rel in files:
        if rel in ALLOWED:
            continue
        got = read_citing(rel)
        if got is None:
            continue
        text, cites = got
        for cite in cites:
            yield rel, text, cite


# ---- verification -----------------------------------------------------------

def relocate(body, anchor, cited_line):
    """Where the recorded anchor text sits now.

    Returns (verdict, line, detail) with verdict one of:
        "here"      the cited line still holds the anchor text
        "shifted"   found uniquely (or nearest-of-N) inside the recorded function
        "moved"     found, but only outside the recorded function
        "gone"      not found at all
    """
    text = anchor["text"]
    want_fn = anchor.get("function")

    if 1 <= cited_line <= len(body) and body[cited_line - 1] == text:
        return "here", cited_line, ""

    hits = [i + 1 for i, line in enumerate(body) if line == text]
    if not hits:
        return "gone", None, ""

    if want_fn is None:
        # File scope: there is no function to scope the search to, so a unique
        # text match is all the evidence available.  More than one and the
        # citation cannot be repaired without a reader.
        if len(hits) == 1:
            return "shifted", hits[0], ""
        return "moved", None, f"{len(hits)} identical lines at file scope"

    scoped = [h for h in hits if enclosing_function(body, h) == want_fn]
    if len(scoped) == 1:
        return "shifted", scoped[0], ""
    if len(scoped) > 1:
        near = min(scoped, key=lambda h: abs(h - cited_line))
        return "shifted", near, (f"nearest of {len(scoped)} identical lines in "
                                 f"{want_fn}()")
    return "moved", None, (f"the text is at :{', :'.join(str(h) for h in hits[:3])}"
                           f"{' ...' if len(hits) > 3 else ''}, outside {want_fn}()")


def verify(citations, index, up, tracked_mode):
    """Check every distinct citation.  Returns (problems, repairs)."""
    anchors = index["anchors"]
    problems = []
    repairs = {}
    for (name, lo), where in sorted(citations.items()):
        key = anchor_key(name, lo)
        anchor = anchors.get(key)
        site = f"{where} cites src/{name}:{lo}"

        if up is None:
            # No tree: the index is all there is to check against.
            if anchor is None and tracked_mode:
                problems.append(f"UPSTREAM_UNANCHORED {site} -- no entry in "
                                f"{INDEX_REL}; run --refresh with an upstream tree")
            continue

        body = up.body(name)
        if body is None:
            problems.append(f"UPSTREAM_UNKNOWN_FILE {site} -- no src/{name} in the "
                            f"upstream tree; renamed, removed, or a typo")
            continue
        if lo < 1 or lo > len(body):
            problems.append(f"UPSTREAM_OUT_OF_RANGE {site} -- src/{name} has "
                            f"{len(body)} lines")
            continue

        if anchor is None:
            # The legacy structural gate, which is everything that can be
            # checked with nothing recorded.  Fatal only in tracked mode,
            # where an anchor could and should exist.
            if tracked_mode:
                problems.append(f"UPSTREAM_UNANCHORED {site} -- no entry in "
                                f"{INDEX_REL}; run --refresh")
            stripped = body[lo - 1].strip()
            if stripped in EMPTY_LINE:
                near = ""
                for delta in (1, -1, 2, -2):
                    cand = lo + delta
                    if 1 <= cand <= len(body) and body[cand - 1].strip() not in EMPTY_LINE:
                        near = (f"; the nearest statement is :{cand}, "
                                f"{body[cand - 1].strip()[:60]!r}")
                        break
                problems.append(f"UPSTREAM_NOT_A_STATEMENT {site} -- that line is "
                                f"{stripped!r}{near}")
            continue

        verdict, line, detail = relocate(body, anchor, lo)
        if verdict == "here":
            continue
        quoted = anchor["text"].strip()[:60]
        if verdict == "shifted":
            repairs[(name, lo)] = line
            problems.append(f"UPSTREAM_CITATION_DRIFTED {site} -- {quoted!r} is now "
                            f"at :{line}{'; ' + detail if detail else ''}")
        elif verdict == "moved":
            problems.append(f"UPSTREAM_CITATION_MOVED {site} -- {quoted!r} is no "
                            f"longer in {anchor.get('function') or 'that file scope'}"
                            f"(); {detail}. Re-read the claim: correct the line "
                            f"number and --refresh, or --reanchor it if it is right")
        else:
            span = (function_span(body, anchor["function"])
                    if anchor.get("function") else None)
            whereabouts = (f"; {anchor['function']}() now spans :{span[0]}-:{span[1]}"
                           if span else "")
            problems.append(f"UPSTREAM_CITATION_STALE {site} -- {quoted!r} is gone "
                            f"from src/{name}{whereabouts}. Upstream changed the "
                            f"line this claim describes. Re-read it: correct the "
                            f"line number and --refresh, or --reanchor it if the "
                            f"claim still holds where it points")
    return problems, repairs


# ---- repair -----------------------------------------------------------------

def apply_repairs(files, repairs):
    """Renumber every drifted citation in place.  Returns (files, occurrences).

    A range citation shifts by the same delta at both ends: the anchor is its
    first line, and a range that outlived the shift spans the same statements.
    """
    touched = occurrences = 0
    for rel in files:
        if rel in ALLOWED:
            continue
        got = read_citing(rel)
        if got is None:
            continue
        text, _ = got
        count = 0

        def repl(m):
            nonlocal count
            key = (m.group("file"), int(m.group("lo")))
            if key not in repairs:
                return m.group(0)
            delta = repairs[key] - key[1]
            count += 1
            out = m.group(0).replace(f":{m.group('lo')}", f":{repairs[key]}", 1)
            if m.group("hi"):
                out = out.replace(f"-{m.group('hi')}",
                                  f"-{int(m.group('hi')) + delta}", 1)
            return out

        fixed = CITATION.sub(repl, text)
        if count:
            (ROOT / rel).write_text(fixed)
            touched += 1
            occurrences += count
    return touched, occurrences


# ---- refresh ----------------------------------------------------------------

def refresh(citations, index, up, reanchor=(), rekey=None, retired=()):
    """Bring the index up to date WITHOUT overwriting an anchor that still stands.

    THE CONSERVATIVE RULE, and the reason this is not a plain regeneration: a
    blanket re-record would, the moment upstream moves, re-anchor every drifted
    citation to whatever statement now happens to sit at that line.  That is
    precisely the error this gate exists to catch, performed automatically and
    committed as evidence.  So:

        a citation with no entry        -- anchored (this is the useful part)
        a citation with an entry        -- left alone, whatever upstream says
        an entry nothing cites          -- dropped
        a key in `rekey`                -- moved to its new line, text intact
        a citation named in `reanchor`  -- re-recorded, deliberately, by hand

    A human who re-reads a STALE citation and writes the corrected line number
    needs no escape hatch: the key changes, the old entry becomes an orphan and
    is dropped, and the new one is anchored like any other new citation.
    `--reanchor` exists for the other case -- upstream edited the statement in
    place, the line number is still right, and a reader has confirmed the claim
    still holds.

    Returns (anchors, problems, added, dropped, rerecorded).
    """
    anchors = {}
    problems = []
    added = rerecorded = 0
    rekey = rekey or {}
    forced = set(reanchor)

    for (name, lo), where in sorted(citations.items()):
        key = anchor_key(name, lo)
        site = f"{where} cites src/{name}:{lo}"

        # A CARRIED ANCHOR OUTRANKS THE STANDING ENTRY FOR ITS NEW KEY, because
        # repairs chain: upstream shifts a block by one, the citation at :1891
        # is repaired to :1885 and the one at :1896 to :1891, and the index
        # still holds :1891's OWN entry from before the shift.  Preferring that
        # entry rebinds the moved citation to the text of the one that used to
        # live there, and the next run reports it as drifted all over again.
        # There is no conflict to lose: if a live citation were still anchored
        # at this key, its text would have to equal the carried text at the
        # same line, which makes it the same citation.
        carried = rekey.get((name, lo)) or index["anchors"].get(key)
        if carried is not None and key not in forced:
            anchors[key] = carried
            continue

        body = up.body(name)
        if body is None:
            problems.append(f"UPSTREAM_UNKNOWN_FILE {site} -- no src/{name} in the "
                            f"upstream tree; renamed, removed, or a typo")
            continue
        if lo < 1 or lo > len(body):
            problems.append(f"UPSTREAM_OUT_OF_RANGE {site} -- src/{name} has "
                            f"{len(body)} lines")
            continue
        line = body[lo - 1]
        if line.strip() in EMPTY_LINE:
            # Refusing here is what keeps the index meaningful: an anchor of
            # `}` matches a thousand lines and relocates to none of them.
            problems.append(f"UPSTREAM_NOT_A_STATEMENT {site} -- that line is "
                            f"{line.strip()!r}; point it at a statement before "
                            f"recording an anchor")
            continue
        anchors[key] = {"text": line, "function": enclosing_function(body, lo)}
        if key in forced:
            rerecorded += 1
        else:
            added += 1

    unused = sorted(forced - set(anchors), key=sort_key)
    for key in unused:
        problems.append(f"UPSTREAM_REANCHOR_UNUSED --reanchor {key} names a citation "
                        f"that nothing in the tracked tree makes")
    # A re-keyed entry moved, it was not dropped, so it is not counted here.
    dropped = len(set(index["anchors"]) - set(anchors) - set(retired))
    return anchors, problems, added, dropped, rerecorded


# ---- the prose that quotes the inventory ------------------------------------

README_REL = "registry/README.md"


def readme_drift(occurrences, distinct):
    """Problems if registry/README.md no longer quotes the live inventory."""
    path = ROOT / README_REL
    if not path.is_file():
        return []
    want = f"{occurrences} occurrences over {distinct} distinct"
    if want in path.read_text():
        return []
    return [f"UPSTREAM_README_DRIFT {README_REL} should say {want!r}; it describes "
            f"the citation inventory this gate guards, so it has to be derived "
            f"from it"]


# ---- main -------------------------------------------------------------------

def collect(files):
    """{(file, line): "rel:lineno"} -- first citing site wins, for the message."""
    citations = {}
    for rel, text, cite in scan(files):
        key = (cite.group("file"), int(cite.group("lo")))
        if key not in citations:
            lineno = text.count("\n", 0, cite.start()) + 1
            citations[key] = f"{rel}:{lineno}"
    return citations


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--paths", nargs="*",
                    help="limit the scan to these paths (default: tracked files). "
                         "An unanchored citation is not an error in this mode: "
                         "case bundles are untracked and cannot be indexed.")
    ap.add_argument("--tree", help="upstream checkout (default: $HDF5_SOURCE_DIR)")
    ap.add_argument("--refresh", action="store_true",
                    help=f"anchor citations that have no entry in {INDEX_REL} and "
                         f"drop entries nothing cites; never overwrites an anchor "
                         f"that is already recorded")
    ap.add_argument("--fix", action="store_true",
                    help="renumber citations that drifted by a pure line shift, "
                         "carrying their anchors across, then --refresh")
    ap.add_argument("--reanchor", nargs="+", metavar="FILE:LINE", default=[],
                    help="re-record these anchors from the current upstream tree. "
                         "For the one case --refresh deliberately will not handle: "
                         "upstream edited the statement in place, the line number "
                         "is still right, and you have re-read the claim.")
    ap.add_argument("--root", help=argparse.SUPPRESS)  # the gate's own test
    args = ap.parse_args()

    if args.root:
        set_root(args.root)
    tree, why = upstream_tree(args.tree)
    tracked_mode = not args.paths
    writing = args.refresh or args.fix or args.reanchor

    if writing and tree is None:
        print(f"UPSTREAM CITATION {'FIX' if args.fix else 'REFRESH'} FAILED: {why}; "
              f"recording an anchor needs the upstream tree")
        return 1
    if writing and args.paths:
        print(f"UPSTREAM CITATION REFRESH FAILED: writing {INDEX_REL} means seeing "
              f"every citation that keeps an entry alive, so it scans the tracked "
              f"set; drop --paths")
        return 1

    files = args.paths if args.paths else tracked_files()
    if files is None:
        print("NOTE not a git checkout; upstream citations unchecked")
        return 0

    index = load_index()
    citations = collect(files)
    up = Upstream(tree) if tree is not None else None
    revision = upstream_revision(tree) if tree is not None else None

    if writing:
        rekey, retired = {}, set()
        touched = renumbered = 0
        if args.fix:
            _, repairs = verify(citations, index, up, tracked_mode)
            # Carry each shifted anchor to its new line BEFORE rewriting, so the
            # repaired citation stays anchored to the same text it always was.
            # Re-recording it from the new line would give the same answer today
            # and launder a mistake tomorrow.
            for (name, lo), new in repairs.items():
                old = anchor_key(name, lo)
                if old in index["anchors"]:
                    rekey[(name, new)] = index["anchors"][old]
                    retired.add(old)
            touched, renumbered = apply_repairs(files, repairs)
            # Re-collect: the numbers on disk changed under us.
            citations = collect(files)

        anchors, problems, added, dropped, rerecorded = refresh(
            citations, index, up, reanchor=args.reanchor, rekey=rekey, retired=retired)

        # `verified_at` is a claim that every anchor below it was observed in
        # that revision, so it may only advance on a run where that is true.
        # Writing it unconditionally would let a --refresh against an OLD
        # checkout -- an easy mistake, and one `--tree` makes easy to repeat --
        # stamp a stale revision onto anchors it never agreed with.
        residual, _ = verify(citations, {"anchors": anchors}, up, tracked_mode)
        drifted = [p for p in residual if "UPSTREAM_CITATION_" in p]
        verified_at = revision if not drifted else index.get("verified_at")
        write_index(anchors, verified_at)

        for p in problems:
            print(p)
        if drifted:
            print(f"NOTE {len(drifted)} anchor(s) do not match upstream {revision}, "
                  f"so verified_at stays at {index.get('verified_at')}. Check the "
                  f"tree is the newest one before reading this as drift.")
        moved = f"renumbered {renumbered} citation(s) in {touched} file(s), " if args.fix else ""
        print(f"UPSTREAM CITATION {'FIX' if args.fix else 'REFRESH'}: {moved}"
              f"anchored {added} new citation(s), re-recorded {rerecorded}, "
              f"dropped {dropped} orphan(s); {len(anchors)} anchor(s) now recorded, "
              f"verified against upstream {verified_at}")
        if problems:
            print(f"UPSTREAM CITATION {'FIX' if args.fix else 'REFRESH'} INCOMPLETE: "
                  f"{len(problems)} citation(s) could not be anchored")
            return 1
        return 0

    problems, repairs = verify(citations, index, up, tracked_mode)

    # An index entry for a citation nobody makes any more is dead weight that
    # hides a real one, so it is drift in its own right.
    stale_entries = []
    if tracked_mode:
        live = {anchor_key(n, l) for (n, l) in citations}
        stale_entries = sorted(set(index["anchors"]) - live, key=sort_key)
        for key in stale_entries:
            problems.append(f"UPSTREAM_ORPHAN_ANCHOR {INDEX_REL} holds {key}, which "
                            f"nothing cites; run --refresh")

    occurrences = sum(1 for _ in scan(files))

    # The prose that describes this gate quotes the size of the thing it
    # guards, and the figure it replaced -- "343 distinct file/line pairs" --
    # was stale by 331 when this was written.  A count nothing derives is a
    # count nobody updates, so derive it.
    if tracked_mode:
        problems += readme_drift(occurrences, len(citations))

    for p in problems:
        print(p)

    if tree is None:
        anchored = sum(1 for (n, l) in citations
                       if anchor_key(n, l) in index["anchors"])
        if problems:
            print(f"UPSTREAM CITATION CHECK FAILED: {len(problems)} problem(s) over "
                  f"{occurrences} citation(s); the content comparison was SKIPPED "
                  f"({why})")
            return 1
        print(f"UPSTREAM CITATION CHECK PARTIAL: {anchored} of {len(citations)} "
              f"distinct citation(s) in {occurrences} place(s) are anchored in "
              f"{INDEX_REL} (recorded against upstream {index.get('verified_at')}); "
              f"content comparison SKIPPED: {why}; set HDF5_SOURCE_DIR to an HDF5 "
              f"checkout to verify the text")
        return 0

    if problems:
        hint = ""
        if repairs:
            hint = (f"\n{len(repairs)} of them are pure line shifts; "
                    f"`python3 tools/check_upstream_citations.py --fix` renumbers "
                    f"them and re-records the index")
        print(f"UPSTREAM CITATION CHECK FAILED: {len(problems)} problem(s) over "
              f"{occurrences} citation(s), against upstream {revision}{hint}")
        return 1
    print(f"UPSTREAM CITATION CHECK OK: {occurrences} libhdf5 line citation(s) in "
          f"{len(citations)} distinct place(s) still hold the text recorded for "
          f"them, against upstream {revision}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
