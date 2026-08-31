#!/usr/bin/env python3
"""_hstar_io — shared, private helpers for the HSTAR KI tools.

Not a user-facing tool (leading underscore keeps it out of the KI-TOOL-INDEX). Everything the
`build_*` tools need to COPY a working HSTAR case and EDIT values in place lives here.

Three hard-won facts this module encodes (see docs/input_preparation.md §0.1):

1. HSTAR input files are read with Fortran LIST-DIRECTED I/O (`read(unit,*) ...`). There is not a
   single FORMAT statement on an input read in the whole source tree. So column positions do not
   matter -- but TOKEN COUNT and LINE ORDER do, absolutely. Delete a header line and every record
   after it shifts by one, silently.
2. The shipped cases are CRLF and carry GBK-encoded Chinese comments. Files are therefore opened
   with encoding="latin-1" (byte-transparent) and the original line ending is preserved on write.
3. A character keyword that lands at end-of-line on a CRLF file absorbs the CR
   ("PARDISO\\r" != "PARDISO"). `GlbDoc.set` never moves a token to end-of-line.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

ENC = "latin-1"  # byte-transparent: round-trips the GBK comment lines untouched

# ---------------------------------------------------------------------------
# Template catalogue -- COPY-FIRST sources. Every entry was executed to EXIT=0
# with the Linux hstar build on 2026-08-26 unless marked otherwise.
# ---------------------------------------------------------------------------
_CASES = Path(os.environ.get("HSTAR_CASES_DIR",
                             "/home/huijun/HSTAR_Next/cases/cases"))

TEMPLATES = {
    "static":                 _CASES / "static",
    "column_selfweight":      _CASES / "test_thermal_expansion",
    "lame_cylinder":          _CASES / "lame_cylinder",
    "cooks_membrane":         _CASES / "cooks_membrane",
    "mini_3d":                _CASES / "mini_3d",
    "train01_gravdam_static": _CASES / "train01_gravdam_static",
    "train02_gravdam_seismic": _CASES / "train02_gravdam_seismic",
    "train03a_modal_dry":     _CASES / "train03a_modal_dry",
    "train05_slope_stability": _CASES / "train05_slope_stability",
    "train07_thermal_transient": _CASES / "train07_thermal_transient",
    "train12_seepage_steady": _CASES / "train12_seepage_steady",
}

# Element type index -> (keyword, nnode, ndimn) -- Elements.f90:128-153 / kinddefine
ELEMENT_INDEX = {
    1: ("L2", 2, 1), 2: ("L3", 3, 1), 3: ("T3", 3, 2), 4: ("T6", 6, 2),
    5: ("Q4", 4, 2), 6: ("Q8", 8, 2), 7: ("H4", 4, 3), 8: ("H10", 10, 3),
    9: ("B8", 8, 3), 10: ("B20", 20, 3), 11: ("T6C3", 6, 2), 12: ("Q8C4", 8, 2),
    13: ("H10C4", 10, 3), 14: ("B20C8", 20, 3), 15: ("T3C3", 3, 2),
    16: ("Q4C4", 4, 2), 17: ("H4C4", 4, 3), 18: ("B8C8", 8, 3), 19: ("L2C2", 2, 1),
    20: ("B2", 2, 1), 21: ("B2C2", 2, 1), 22: ("P4", 4, 2), 23: ("PR6", 6, 3),
    24: ("PR6C6", 6, 3), 25: ("STEEL", 2, 1), 26: ("THIN_FILM", 4, 2),
}

# Degree-of-freedom index -> title, from Global.f90 title(1:10)
DOF_TITLE = {1: "Ux", 2: "Uy", 3: "Uz", 4: "Thx", 5: "Thy", 6: "Thz",
             7: "Hydrostatic_pressure", 8: "Pore_Pressure", 9: "Air_Pressure",
             10: "Temperature"}


class HstarInputError(ValueError):
    """A structural problem in an HSTAR input file or in a requested edit."""


# ---------------------------------------------------------------------------
# plain text file helpers
# ---------------------------------------------------------------------------
def read_lines(path):
    """Read an HSTAR text file, returning (lines_without_terminator, terminator)."""
    raw = Path(path).read_text(encoding=ENC)
    eol = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.replace("\r\n", "\n").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines, eol


def write_lines(path, lines, eol="\n"):
    Path(path).write_text(eol.join(lines) + eol, encoding=ENC)


def raw_tokens(line):
    """Split one record the way Fortran list-directed input does.

    Handles the four dialect features that appear in the shipped HSTAR cases and that a naive
    `.split()` gets wrong (all four verified in cases/train05_slope_stability/1.glb):

      * quoted strings           'Q','PARDISO','MAT_DE'   -> Q PARDISO MAT_DE
      * comma and tab separators
      * a trailing `!` annotation ( `0 0 0 ... ! order to time` ) -- list-directed input would
        stop earlier because it already has all its values, so everything from `!` is dropped
      * a bare `/` terminates the read
    """
    out, buf, quote = [], "", ""
    for ch in line:
        if quote:
            if ch == quote:
                out.append(buf)
                buf, quote = "", ""
            else:
                buf += ch
            continue
        if ch in "'\"":
            if buf:
                out.append(buf)
                buf = ""
            quote = ch
            continue
        if ch in " \t,":
            if buf:
                out.append(buf)
                buf = ""
            continue
        if ch == "!" and not buf:
            break
        if ch == "/" and not buf:
            break
        buf += ch
    if buf:
        out.append(buf)
    while out and out[-1].startswith("!"):
        out.pop()
    return out


def expand(toks):
    """Expand Fortran repeat counts: `337*0` -> 337 copies of `0`, `4*1` -> 1 1 1 1."""
    out = []
    for t in toks:
        if "*" in t and not t.startswith("*"):
            head, _, tail = t.partition("*")
            if head.isdigit():
                n = int(head)
                if n > 100000:
                    raise HstarInputError(f"implausible repeat count in {t!r}")
                out.extend([tail] * n if tail else [""] * n)
                continue
        out.append(t)
    return out


def tokens(line):
    """List-directed tokenisation with quote handling and repeat-count expansion."""
    return expand(raw_tokens(line))


def copy_template(template, dest, overwrite=False):
    """COPY-FIRST: duplicate a whole working case directory.

    template: a key of TEMPLATES or a path to a case directory.
    Returns the destination Path.
    """
    src = TEMPLATES.get(template, Path(str(template)))
    src = Path(src)
    if not src.is_dir():
        raise HstarInputError(
            f"template case directory not found: {src}. Known templates: "
            f"{sorted(TEMPLATES)}. Set HSTAR_CASES_DIR if the case library moved.")
    if not (src / "inp").is_file():
        raise HstarInputError(f"{src} is not an HSTAR case: no 'inp' file")
    dest = Path(dest)
    if dest.exists():
        if not overwrite:
            raise HstarInputError(f"destination already exists: {dest} (pass overwrite=True)")
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    # Templates are read-only in the case library; make the working copy writable.
    for p in dest.rglob("*"):
        if p.is_file():
            p.chmod(p.stat().st_mode | 0o200)
    return dest


def probn_of(case_dir):
    """The case base name, read from `inp` line 4 (Fem.f90:92-97)."""
    lines, _ = read_lines(Path(case_dir) / "inp")
    if len(lines) < 5:
        raise HstarInputError(
            f"{case_dir}/inp has {len(lines)} lines; HSTAR reads 5 "
            "(text / flags / text / probn / runblks)")
    return tokens(lines[3])[0]


def set_inp(case_dir, restart=None, relis=None, sysrelis=None, adina=None,
            uopt_r=None, gamamax=None, probn=None, runblks=None):
    """Edit `inp` in place. Any argument left None keeps the template's value."""
    p = Path(case_dir) / "inp"
    lines, eol = read_lines(p)
    if len(lines) < 5:
        raise HstarInputError(f"{p} has {len(lines)} lines, needs 5")
    flags = tokens(lines[1])
    if len(flags) < 6:
        raise HstarInputError(
            f"{p} line 2 has {len(flags)} tokens, HSTAR reads 6 "
            "(restart relis sysrelis ADINA Uopt_R gamamax)")
    for i, v in enumerate([restart, relis, sysrelis, adina, uopt_r, gamamax]):
        if v is not None:
            flags[i] = str(int(v))
    lines[1] = "  " + "  ".join(flags)
    if probn is not None:
        lines[3] = str(probn)
    if runblks is not None:
        lines[4] = str(int(runblks))
    write_lines(p, lines, eol)
    return p


# ---------------------------------------------------------------------------
# probn.glb -- the master control file
# ---------------------------------------------------------------------------
# Each entry: (field-name-tuple, "conditional python expr or None")
# The parser below replays Global.f90's read sequence so that every scalar can be
# located by (line index, token index) even when the conditional records change.
_GLB_HEAD = [
    ("npoin npoinb nelem ndimn nmats ngroup ntlink outplot kstab mat_curve "
     "meshc rmesh level_set_problem ljdp stab_matde"),
    ("ninit kinit winit nblks nlinks nonsym outinp outintr outintw neuman equvs "
     "type_ABC block_stab nbackf nbspring ebody outind nbackdT ninistn"),
    ("type_problem type_solver type_load type_nl stabpw nlayer kglb state_change "
     "Bparameter balgor upliftin"),
    ("nmass nsmat nhmat nqmat nldfl kgmat nswkw uwcpl ngrav nflow ECWPIPE"),
    ("ntsmat nthmat kstat ground_inf src nextrf submodel"),
]

_INT_FIELDS = {
    "npoin", "npoinb", "nelem", "ndimn", "nmats", "ngroup", "ntlink", "mat_curve",
    "meshc", "rmesh", "level_set_problem", "ljdp", "ninit", "kinit", "winit",
    "nblks", "nlinks", "nonsym", "outinp", "outintr", "outintw", "neuman", "equvs",
    "block_stab", "nbackf", "nbspring", "ebody", "outind", "nbackdT", "ninistn",
    "type_nl", "stabpw", "nlayer", "kglb", "state_change", "Bparameter", "balgor",
    "upliftin", "nmass", "nsmat", "nhmat", "nqmat", "nldfl", "kgmat", "nswkw",
    "uwcpl", "ngrav", "nflow", "ECWPIPE", "ntsmat", "nthmat", "kstat", "ground_inf",
    "src", "nextrf", "submodel", "mdofn",
}
_CHAR_FIELDS = {"outplot", "type_ABC", "type_problem", "type_solver", "type_load"}


class GlbDoc:
    """A parsed, editable `probn.glb`.

    The parser replays the read sequence in Global.f90:640-960 so that a named scalar
    resolves to an exact (line, token) position in the ORIGINAL file. Edits rewrite that
    token only -- the rest of the file, including every header/echo line and every
    conditional record, is preserved byte-for-byte.
    """

    def __init__(self, path):
        self.path = Path(path)
        self.lines, self.eol = read_lines(self.path)
        self.pos = {}          # field name -> (line index, token index)
        self.value = {}        # field name -> string token as found
        self.section = {}      # section name -> line index of its first value line
        self._parse()

    # -- parsing ----------------------------------------------------------
    def _next_value_line(self, i):
        """Index of the next line at or after i (headers are consumed explicitly)."""
        if i >= len(self.lines):
            raise HstarInputError(f"{self.path}: ran off the end while parsing")
        return i

    def _bind(self, li, names):
        tk = tokens(self.lines[li])
        if len(tk) < len(names):
            raise HstarInputError(
                f"{self.path}:{li + 1} has {len(tk)} tokens but HSTAR reads "
                f"{len(names)} ({' '.join(names)}). A short control line makes the "
                f"list-directed read spill onto the next record and corrupts everything after it.")
        for k, n in enumerate(names):
            self.pos[n] = (li, k)
            self.value[n] = tk[k]

    def _parse(self):
        i = 0
        i += 1                                          # text
        self._bind(i, _GLB_HEAD[0].split()); i += 1
        rmesh = int(self.value["rmesh"])
        i += 1                                          # text 'valv1'
        if rmesh != 0:
            self._bind(i, ["valv1", "valv2"]); i += 1
        i += 1                                          # text 'ndivide'
        if rmesh != 0:
            self.section["ndefault"] = i; i += 1
        i += 1                                          # text
        self._bind(i, _GLB_HEAD[1].split()); i += 1
        i += 1                                          # text
        self._bind(i, _GLB_HEAD[2].split()); i += 1
        i += 1                                          # text 'type_layer1'
        if int(self.value["nlayer"]) == 2:
            self._bind(i, ["type_nl_layer1", "type_nl_layer2", "solver_iter"]); i += 1
        i += 1                                          # text
        self._bind(i, _GLB_HEAD[3].split()); i += 1
        i += 1                                          # text 'nfreeflownode'
        if int(self.value["nflow"]) != 0:
            self._bind(i, ["nfreeflownode"])
            nff = int(self.value["nfreeflownode"]); i += 1
            if nff != 0:
                self.section["listfreeflownode"] = i; i += 1
        i += 1                                          # text
        self._bind(i, _GLB_HEAD[4].split()); i += 1
        i += 1                                          # text 'MDOFN'
        self._bind(i, ["mdofn"]); i += 1
        mdofn = int(self.value["mdofn"])
        self.section["lmdofn"] = i; i += 1
        self.section["order_time_mdofn"] = i; i += 1
        i += 1                                          # text
        self._bind(i, ["beeta1", "beeta2", "theta1"]); i += 1
        ngroup, nblks = int(self.value["ngroup"]), int(self.value["nblks"])
        for name, nrows in (("equvs_process", 1), ("appear_level", 1),
                            ("appear_process", nblks), ("matno_process", nblks),
                            ("force_process", 1), ("average_appear", 1)):
            i += 1                                      # text
            self.section[name] = i
            self.section[name + "_nrows"] = nrows
            for r in range(nrows):
                tk = tokens(self.lines[i + r])
                if len(tk) < ngroup:
                    raise HstarInputError(
                        f"{self.path}:{i + r + 1}: {name} row has {len(tk)} values, "
                        f"ngroup={ngroup}")
            i += nrows
        self.section["_after_average_appear"] = i
        self.mdofn, self.ngroup, self.nblks = mdofn, ngroup, nblks

    # -- editing ----------------------------------------------------------
    def get(self, name):
        if name not in self.value:
            raise HstarInputError(f"unknown .glb field {name!r}; known: {sorted(self.value)}")
        return self.value[name]

    def set(self, name, value):
        """Replace one scalar, preserving the token's field width where possible."""
        if name not in self.pos:
            raise HstarInputError(
                f"unknown or not-present .glb field {name!r}. Known fields: "
                f"{sorted(self.pos)}. (Conditional records only appear when their "
                f"switch is on -- e.g. valv1/valv2 need rmesh/=0.)")
        if name in _INT_FIELDS:
            new = str(int(value))
        elif name in _CHAR_FIELDS:
            new = str(value).strip()
            if not new:
                raise HstarInputError(f"{name} may not be blank")
        else:
            new = (f"{float(value):.6E}" if isinstance(value, float) else str(value))
        li, ti = self.pos[name]
        tk = tokens(self.lines[li])          # quote-stripped, repeat-expanded
        tk[ti] = new
        if name in _CHAR_FIELDS and ti == len(tk) - 1 and self.eol == "\r\n":
            raise HstarInputError(
                f"refusing to write character field {name!r} as the last token of a CRLF "
                f"line: Fortran would read it as {new!r}+CR and silently miss the branch")
        # Rewrite the WHOLE record from the expanded token list. Rewriting rather than
        # patching in place is what makes repeat counts (`4*1`) and quoted keywords
        # (`'PARDISO'`) safe to edit: the expanded form is always a legal list-directed
        # record, and no token can end up merged with its neighbour.
        self.lines[li] = "  " + "  ".join(tk)
        self.value[name] = new
        return self

    def set_row(self, section, row, values):
        """Rewrite one row of a per-group matrix (appear_process, matno_process, ...)."""
        if section not in self.section:
            raise HstarInputError(f"unknown .glb section {section!r}")
        nrows = self.section.get(section + "_nrows", 1)
        if not 0 <= row < nrows:
            raise HstarInputError(f"{section} has {nrows} row(s); row={row} out of range")
        if len(values) != self.ngroup:
            raise HstarInputError(
                f"{section} row needs ngroup={self.ngroup} values, got {len(values)}")
        li = self.section[section] + row
        self.lines[li] = "  " + "  ".join(f"{int(v):>9d}" for v in values)
        return self

    def get_row(self, section, row=0):
        li = self.section[section] + row
        return [int(t) for t in tokens(self.lines[li])[:self.ngroup]]

    def find(self, needle, start=0):
        """Index of the first line containing `needle` (used for the sections after
        average_appear, which are located by their header text rather than by replay)."""
        for i in range(start, len(self.lines)):
            if needle in self.lines[i]:
                return i
        raise HstarInputError(f"{self.path}: no line containing {needle!r}")

    def save(self, path=None):
        write_lines(path or self.path, self.lines, self.eol)
        return path or self.path


# ---------------------------------------------------------------------------
# small shared validators
# ---------------------------------------------------------------------------
def require(cond, msg):
    if not cond:
        raise HstarInputError(msg)


def check_consistent(case_dir):
    """Cross-check .glb counts against .cor / .ele record counts.

    This is the single most valuable pre-run check: HSTAR allocates from the .glb counts
    and then reads that many records, so a mismatch is either an EOF crash (too few) or a
    silently truncated mesh (too many).
    """
    case_dir = Path(case_dir)
    probn = probn_of(case_dir)
    g = GlbDoc(case_dir / f"{probn}.glb")
    problems = []
    ncor, _ = read_lines(case_dir / f"{probn}.cor")
    ncor = [l for l in ncor if tokens(l)]
    nele, _ = read_lines(case_dir / f"{probn}.ele")
    nele = [l for l in nele if tokens(l)]
    if len(ncor) != int(g.get("npoin")):
        problems.append(f".cor has {len(ncor)} records but .glb npoin={g.get('npoin')}")
    if len(nele) != int(g.get("nelem")):
        problems.append(f".ele has {len(nele)} records but .glb nelem={g.get('nelem')}")
    ndimn = int(g.get("ndimn"))
    for k, l in enumerate(ncor[:50]):
        if len(tokens(l)) < 1 + ndimn:
            problems.append(f".cor line {k + 1}: {len(tokens(l))} tokens, "
                            f"need 1+ndimn={1 + ndimn}")
            break
    return {"probn": probn, "npoin": int(g.get("npoin")), "nelem": int(g.get("nelem")),
            "ndimn": ndimn, "ngroup": g.ngroup, "nblks": g.nblks,
            "type_problem": g.get("type_problem"), "type_solver": g.get("type_solver"),
            "problems": problems, "ok": not problems}
