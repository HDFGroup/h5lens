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

"""Regression checks for the upstream line-citation gate.

Driven against a SYNTHETIC upstream tree rather than the real one: the real
checkout moves under us, so a test anchored to it would fail for the same reason
the gate exists to report about prose.  The synthetic tree makes each case exact
-- this line shifted, this statement was edited away -- and keeps the test
runnable where no HDF5 checkout exists.

TWO synthetic trees, BEFORE and AFTER, standing in for an upstream that moved.
Anchors are recorded against BEFORE and then checked against AFTER, which is
the only way to exercise the thing the index exists for.  Each of the four
outcomes is a separate statement in the fixture, so one upstream edit cannot
mask another:

    shift_me()   survives, two lines lower       -> DRIFTED, and --fix repairs it
    edit_me()    rewritten in place              -> STALE
    move_me()    same text, different function   -> MOVED
    keep_me()    untouched                       -> silent, the positive control

THE CITING TREE IS A REAL GIT REPOSITORY in a temp directory, reached with
--root.  That is not ceremony: `--fix` rewrites tracked files in place, so it
cannot be exercised against this repository without editing it, and an untested
repair tool is one nobody dares run.

THE SKIP PATH is a case too, and still the important one: this gate used to be
green-by-absence whenever HDF5_SOURCE_DIR was unset.  It no longer is -- the
index is checkable without any tree -- so the test pins both halves: the skip
says SKIPPED and never OK, and an unanchored citation still fails with no tree
at all.

NO CITATION IS SPELLED OUT IN THIS FILE.  Every one is interpolated from a
derived name, because a literal here would be scanned by the very gate under
test and reported as a citation of a file that does not exist upstream.  That
is not a hypothetical: the sibling pickle gate landed with exactly that defect
and its own test was the only thing failing it.
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools" / "check_upstream_citations.py"
ENV = {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent",
       "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"}
INDEX_REL = "registry/upstream-citations.json"

# BEFORE.  Every outcome is a separate statement, and `keep_me` sits ABOVE the
# place upstream will insert at, so it is genuinely untouched rather than merely
# lucky -- an "unchanged" control that shifts with everything else controls for
# nothing.  `shift_me` and `also_shifts` are ADJACENT on purpose: upstream
# inserts exactly one line, so `shift_me` is repaired onto the line
# `also_shifts` is vacating, which is the collision that broke the first
# full-scale --fix.
BEFORE = """\
/* synthetic upstream */
int
alpha(void)
{
    return keep_me();
    return edit_me();
    return shift_me();
    return also_shifts();

}
int
beta(void)
{
    return move_me();
}
"""

# AFTER.  `edit_me` was rewritten where it stood, ONE line was inserted below
# it, and `move_me` was relocated out of `beta` into `alpha`.
AFTER = """\
/* synthetic upstream */
int
alpha(void)
{
    return keep_me();
    return edit_me_differently();
    /* a line upstream inserted */
    return shift_me();
    return also_shifts();
    return move_me();

}
int
beta(void)
{
    return nothing();
}
"""

KEPT = 5                                 # return keep_me();   -- same line in both
EDITED = 6                               # rewritten in place, so same line number
SHIFTED_BEFORE, SHIFTED_AFTER = 7, 8     # return shift_me();
ALSO_BEFORE, ALSO_AFTER = 8, 9           # return also_shifts();  -- the collision
BLANK_BEFORE, BRACE_BEFORE = 9, 10       # the blank line and the bare brace
MOVED_BEFORE, MOVED_AFTER = 14, 10       # return move_me();  -- beta() to alpha()
PAST_EOF = 500


def build_tree(parent, name, body, source):
    """A directory the checker accepts as an HDF5 checkout."""
    src = Path(parent) / name / "src"
    src.mkdir(parents=True)
    (src / "H5public.h").write_text("#define H5_VERS_MAJOR 9\n"
                                    "#define H5_VERS_MINOR 9\n"
                                    "#define H5_VERS_RELEASE 9\n")
    (src / source).write_text(body)
    return src.parent


def absent_name(src):
    """A source name the synthetic trees do not contain, derived not written."""
    for n in itertools.count():
        name = f"H5Absent{n}.c"
        if not (src / "src" / name).exists():
            return name


def git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True,
                   capture_output=True, text=True, env=ENV)


def build_citing(parent):
    """A git repository that cites the synthetic upstream file."""
    root = Path(parent) / "citing"
    (root / "registry").mkdir(parents=True)
    git_init = subprocess.run(["git", "init", "-q", str(root)],
                              capture_output=True, text=True, env=ENV)
    assert git_init.returncode == 0, git_init.stderr
    return root


def write_citations(root, source, lines):
    """Put one citation per line into a tracked file, and track it."""
    body = "".join(f"# claim {i}: see src/{source}:{ln} for the check\n"
                   for i, ln in enumerate(lines))
    (root / "claims.yml").write_text(body)
    git(root, "add", "claims.yml")
    return body


def run(root, tree, *extra):
    cmd = [sys.executable, str(CHECKER), "--root", str(root)]
    if tree is not None:
        cmd += ["--tree", str(tree)]
    out = subprocess.run(cmd + list(extra), capture_output=True, text=True,
                         cwd=str(ROOT), env=ENV)
    return out.stdout + out.stderr


def run_paths(probe, tree):
    out = subprocess.run([sys.executable, str(CHECKER), "--paths", str(probe),
                          "--tree", str(tree)],
                         capture_output=True, text=True, cwd=str(ROOT), env=ENV)
    return out.stdout + out.stderr


def main() -> int:
    source = "H5" + "Synthetic" + ".c"
    with tempfile.TemporaryDirectory() as tmp:
        before = build_tree(tmp, "before", BEFORE, source)
        after = build_tree(tmp, "after", AFTER, source)
        root = build_citing(tmp)
        index = root / INDEX_REL

        def check(label, cond, out):
            assert cond, f"{label}\n{out}"
            print(f"  ok: {label}")

        # ---- recording ------------------------------------------------------
        write_citations(root, source,
                        [KEPT, EDITED, SHIFTED_BEFORE, ALSO_BEFORE, MOVED_BEFORE])
        out = run(root, before, "--refresh")
        check("--refresh anchors every citation that had none",
              "anchored 5 new citation(s)" in out, out)
        anchors = json.loads(index.read_text())["anchors"]
        check("each anchor records the cited text and its function",
              anchors[f"{source}:{SHIFTED_BEFORE}"]["text"].strip() == "return shift_me();"
              and anchors[f"{source}:{SHIFTED_BEFORE}"]["function"] == "alpha",
              json.dumps(anchors, indent=2))

        # POSITIVE CONTROL.  Without it the negatives prove nothing: a checker
        # that rejected everything would pass all of them.
        out = run(root, before)
        check("citations verify against the tree they were anchored to",
              "UPSTREAM CITATION CHECK OK" in out and "UPSTREAM_" not in
              out.replace("UPSTREAM CITATION CHECK OK", ""), out)

        # THE INDEX MUST NOT CITE ITSELF.  Its keys are spelled exactly like
        # citations, so a tracked index doubles the inventory and -- far worse
        # -- `--fix` renumbers the KEYS while the text they record stays put,
        # rebinding every anchor to a line it never described.  Found by running
        # --fix at full scale rather than by reading, so it is pinned here.
        git(root, "add", INDEX_REL)
        out = run(root, before)
        check("a tracked index is not scanned as a citing file",
              "OK: 5 libhdf5 line citation(s) in 5 distinct place(s)" in out, out)

        # ---- the four outcomes, against a moved upstream --------------------
        out = run(root, after)
        for tag, what in (("UPSTREAM_CITATION_DRIFTED", "a pure line shift"),
                          ("UPSTREAM_CITATION_STALE", "a statement edited away"),
                          ("UPSTREAM_CITATION_MOVED", "text now in another function")):
            check(f"{what} is reported as {tag}", tag in out, out)
        check("the drift report names the line to move to",
              f"is now at :{SHIFTED_AFTER}" in out, out)
        check("a stale citation is told where its function went now",
              "alpha() now spans" in out or "beta() now spans" in out, out)
        check("the failure says how many are mechanically repairable",
              "pure line shifts" in out, out)
        check("the untouched citation is not reported",
              out.count("UPSTREAM_CITATION_") == 4, out)

        # ---- --refresh must not launder drift -------------------------------
        # The whole design rests on this: a blanket re-record would re-anchor
        # the drifted citation to whatever now sits at that line and report a
        # clean tree.
        before_refresh = index.read_text()
        out = run(root, after, "--refresh")
        check("--refresh leaves a standing anchor alone even when it no longer matches",
              index.read_text() == before_refresh, out)
        # The same run must not stamp the disagreeing revision onto the index
        # either: pointing --tree at the wrong checkout is an easy mistake, and
        # that stamp is what a later reader trusts.
        check("a --refresh that does not verify leaves verified_at where it was",
              "verified_at stays at" in out, out)
        out = run(root, after)
        check("so the drift is still reported after a --refresh",
              "UPSTREAM_CITATION_DRIFTED" in out, out)
        out = run(root, before, "--refresh")
        check("a --refresh that does verify advances verified_at",
              "verified_at stays at" not in out, out)

        # ---- --fix ----------------------------------------------------------
        out = run(root, after, "--fix")
        check("--fix renumbers the shifted citation",
              "renumbered 2 citation(s)" in out, out)
        text = (root / "claims.yml").read_text()
        check("the citing file now names the new lines",
              f"{source}:{SHIFTED_AFTER}" in text and f"{source}:{ALSO_AFTER}" in text
              and f"{source}:{SHIFTED_BEFORE}" not in text, text)
        anchors = json.loads(index.read_text())["anchors"]
        # THE COLLISION, and the reason the two citations are adjacent: `shift_me`
        # was repaired onto the line `also_shifts` is vacating, so the index
        # still held that line's OWN pre-shift entry.  Preferring it rebinds the
        # moved citation to the text of the one that used to live there, and the
        # next run reports drift no --fix can ever settle.  Reverting the
        # precedence alone fails exactly here.
        check("a repair onto a line another citation is vacating keeps its own anchor",
              anchors[f"{source}:{SHIFTED_AFTER}"]["text"].strip() == "return shift_me();",
              json.dumps(anchors, indent=2))
        # The ordinary case, onto a line nothing was anchored at.
        check("a repair onto a free line carries its anchor across too",
              anchors[f"{source}:{ALSO_AFTER}"]["text"].strip() == "return also_shifts();",
              json.dumps(anchors, indent=2))
        check("--fix does not re-anchor the citations that need a reader",
              anchors[f"{source}:{EDITED}"]["text"].strip() == "return edit_me();",
              json.dumps(anchors, indent=2))
        out = run(root, after)
        check("after --fix only the two that need a reader remain",
              out.count("UPSTREAM_CITATION_") == 2
              and "UPSTREAM_CITATION_DRIFTED" not in out, out)

        # ---- --reanchor -----------------------------------------------------
        out = run(root, after, "--reanchor", f"{source}:{EDITED}")
        check("--reanchor re-records exactly the citation it is given",
              "re-recorded 1" in out, out)
        anchors = json.loads(index.read_text())["anchors"]
        check("the re-anchored entry now holds the current upstream text",
              anchors[f"{source}:{EDITED}"]["text"].strip()
              == "return edit_me_differently();", json.dumps(anchors, indent=2))
        out = run(root, after)
        check("the re-anchored citation stops being reported",
              "UPSTREAM_CITATION_STALE" not in out, out)
        out = run(root, after, "--reanchor", f"{source}:{PAST_EOF}")
        check("--reanchor of a citation nobody makes is refused",
              "UPSTREAM_REANCHOR_UNUSED" in out, out)

        # ---- correcting a number by hand needs no escape hatch --------------
        write_citations(root, source,
                        [KEPT, EDITED, SHIFTED_AFTER, ALSO_AFTER, MOVED_AFTER])
        out = run(root, after, "--refresh")
        check("a hand-corrected line number anchors itself and retires the old entry",
              "anchored 1 new citation(s)" in out and "dropped 1 orphan(s)" in out, out)

        # ---- the orphan rule ------------------------------------------------
        write_citations(root, source, [SHIFTED_AFTER])
        out = run(root, after)
        check("an index entry nothing cites any more is reported",
              "UPSTREAM_ORPHAN_ANCHOR" in out, out)
        run(root, after, "--refresh")
        out = run(root, after)
        check("and --refresh drops it", "UPSTREAM_ORPHAN_ANCHOR" not in out, out)

        # ---- an unanchored citation in the tracked tree ---------------------
        write_citations(root, source, [SHIFTED_AFTER, KEPT, EDITED])
        out = run(root, after)
        check("a citation added without anchoring is caught",
              "UPSTREAM_UNANCHORED" in out, out)

        # ---- the prose that quotes the inventory ----------------------------
        # The figure this replaced in registry/README.md was stale by 331, which
        # is what a hand-maintained count of a growing thing does.
        readme = root / "registry" / "README.md"
        readme.write_text("cites 99 occurrences over 99 distinct file/line pairs\n")
        out = run(root, after)
        check("a README that misquotes the citation inventory is caught",
              "UPSTREAM_README_DRIFT" in out, out)
        readme.write_text("cites 3 occurrences over 3 distinct file/line pairs\n")
        out = run(root, after)
        check("and passes once it quotes the derived figure",
              "UPSTREAM_README_DRIFT" not in out, out)
        readme.unlink()

        # ---- no tree: partial, not green-by-absence -------------------------
        out = run(root, None)
        check("an unanchored citation fails with no upstream tree at all",
              "UPSTREAM_UNANCHORED" in out and "SKIPPED" in out
              and "CHECK OK" not in out, out)
        run(root, after, "--refresh")
        out = run(root, None)
        check("an anchored tree reports PARTIAL and says what was skipped",
              "UPSTREAM CITATION CHECK PARTIAL" in out
              and "SKIPPED" in out and "HDF5_SOURCE_DIR" in out
              and "CHECK OK" not in out, out)

        # ---- the unanchored structural gate, via --paths --------------------
        # Case bundles are untracked, so they can hold no anchor; the legacy
        # rule is all that can be applied to them, and it still applies.
        probe = Path(tmp) / "bundle.yml"
        cite = lambda ln, f=source: probe.write_text(
            f"# see src/{f}:{ln} for the check\n")

        cite(SHIFTED_BEFORE)
        out = run_paths(probe, before)
        check("an unanchored citation of a real statement passes",
              "UPSTREAM CITATION CHECK OK" in out, out)
        cite(f"{SHIFTED_BEFORE}-{BRACE_BEFORE}")
        out = run_paths(probe, before)
        check("a range citation is judged on its first line",
              "UPSTREAM CITATION CHECK OK" in out, out)
        for label, ln, tag in (
                ("a blank line", BLANK_BEFORE, "UPSTREAM_NOT_A_STATEMENT"),
                ("a bare brace", BRACE_BEFORE, "UPSTREAM_NOT_A_STATEMENT"),
                ("a line past the end", PAST_EOF, "UPSTREAM_OUT_OF_RANGE")):
            cite(ln)
            out = run_paths(probe, before)
            check(f"an unanchored citation of {label} is caught", tag in out, out)
        probe.write_text(f"# see src/{absent_name(before)}:{SHIFTED_BEFORE} here\n")
        out = run_paths(probe, before)
        check("a citation of a file not in the tree is caught",
              "UPSTREAM_UNKNOWN_FILE" in out, out)

        # The nearest-statement hint is what makes a failure a grep rather than
        # an archaeology exercise, so it is part of the contract.
        cite(BLANK_BEFORE)
        out = run_paths(probe, before)
        check("the failure names the nearest statement",
              f"the nearest statement is :{ALSO_BEFORE}" in out, out)

        # ---- writing needs a tree, and the whole tracked set ----------------
        out = run(root, None, "--refresh")
        check("--refresh without a tree is refused, not silently skipped",
              "REFRESH FAILED" in out and "HDF5_SOURCE_DIR" in out, out)
        out = subprocess.run(
            [sys.executable, str(CHECKER), "--root", str(root), "--tree", str(after),
             "--refresh", "--paths", str(probe)],
            capture_output=True, text=True, cwd=str(ROOT), env=ENV)
        check("--refresh with --paths is refused: it would drop every other anchor",
              "REFRESH FAILED" in out.stdout, out.stdout + out.stderr)

    print("UPSTREAM CITATION GATE TEST OK: anchors record, drift is classified four "
          "ways against a moved upstream, --fix repairs only pure line shifts and "
          "carries anchors across, --refresh refuses to launder the rest, "
          "--reanchor is explicit, and the no-tree path is partial rather than green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
