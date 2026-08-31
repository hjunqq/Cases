#!/usr/bin/env python3
"""
hstar_io.py -- record-level primitives shared by every HSTAR tool.

HSTAR reads all of its text inputs list-directed (`read(unit,*)`), so the files
are RECORD-oriented, not column-oriented: token order and the number of records
are rigid, whitespace is not.  Two consequences are encoded here.

1. `read_tokens` expands Fortran repeat counts (`10*0`, `9*0.`, `3*1.0e-05`),
   which appear in shipped cases and are legal list-directed input.

2. `GlbFile` edits `*.glb` by ANCHORED RECORD REPLACEMENT: locate the heading
   record by a substring, replace the data record that follows it.  It never
   regenerates the file.  Heading records are positional -- `read(gunit,*)text`
   consumes one record and discards it -- so deleting or adding one shifts
   every subsequent read by one record and produces a silent misparse.

Self-test:  python3 hstar_io.py --selftest
"""

import os
import re
import shutil

_REPEAT = re.compile(r"^(\d+)\*(.*)$")


def read_tokens(line):
    """Split one list-directed record into tokens, expanding `n*value`.

    >>> read_tokens("  1  2  3*0.0  ")
    ['1', '2', '0.0', '0.0', '0.0']
    >>> read_tokens("10*0")
    ['0'] * 10 -> ten '0'
    """
    out = []
    for tok in line.replace(",", " ").split():
        m = _REPEAT.match(tok)
        if m:
            n = int(m.group(1))
            val = m.group(2)
            if val == "":          # bare `n*` means n null values -> unchanged
                continue
            out.extend([val] * n)
        else:
            out.append(tok)
    return out


def fmt_int(v, w=6):
    return "%*d" % (w, int(v))


def fmt_real(v, w=18, p=10):
    return "%*.*f" % (w, p, float(v))


def fmt_sci(v):
    return "%15.5E" % float(v)


def rec_ints(vals, w=6):
    return "".join(fmt_int(v, w) for v in vals)


def rec_mixed(vals):
    """Emit a record of mixed ints/floats/strings, whitespace separated."""
    parts = []
    for v in vals:
        if isinstance(v, bool):
            parts.append("1" if v else "0")
        elif isinstance(v, int):
            parts.append(str(v))
        elif isinstance(v, float):
            parts.append("%.6E" % v)
        else:
            parts.append(str(v))
    return "  " + "  ".join(parts)


class GlbFile(object):
    """Anchored editor for `*.glb` (and any other heading/data HSTAR file)."""

    def __init__(self, path):
        self.path = path
        with open(path, "r", errors="replace") as fh:
            self.lines = fh.read().split("\n")
        if self.lines and self.lines[-1] == "":
            self.lines.pop()
            self._trailing_nl = True
        else:
            self._trailing_nl = True

    # ---- locating -------------------------------------------------------
    def find_heading(self, anchor, start=0):
        """Index of the first record containing `anchor` (case-insensitive)."""
        a = anchor.lower()
        for i in range(start, len(self.lines)):
            if a in self.lines[i].lower():
                return i
        raise KeyError(
            "heading record %r not found in %s -- the template is not the one "
            "this tool expects (triplet dt_005)" % (anchor, self.path))

    def get_after(self, anchor, offset=1, start=0):
        i = self.find_heading(anchor, start) + offset
        return self.lines[i]

    # ---- editing --------------------------------------------------------
    def replace_after(self, anchor, new_record, offset=1, start=0):
        """Replace the record `offset` lines below the heading `anchor`."""
        i = self.find_heading(anchor, start) + offset
        if i >= len(self.lines):
            raise IndexError("anchor %r has no data record below it" % anchor)
        self.lines[i] = new_record
        return i

    def set_field_after(self, anchor, index, value, offset=1, start=0):
        """Replace ONE token of the data record below `anchor`, keeping the rest.

        This is the safest edit: it cannot change the token count, which is
        what a list-directed reader is sensitive to.
        """
        i = self.find_heading(anchor, start) + offset
        toks = read_tokens(self.lines[i])
        if index >= len(toks):
            raise IndexError(
                "record below %r has %d tokens, cannot set index %d"
                % (anchor, len(toks), index))
        toks[index] = str(value)
        self.lines[i] = "  " + "  ".join(toks)
        return i

    def tokens_after(self, anchor, offset=1, start=0):
        return read_tokens(self.get_after(anchor, offset, start))

    def save(self, path=None):
        p = path or self.path
        with open(p, "w") as fh:
            fh.write("\n".join(self.lines))
            if self._trailing_nl:
                fh.write("\n")
        return p


def copy_template(src_dir, dst_dir, overwrite=False):
    """COPY-FIRST: clone a complete working case directory."""
    if os.path.exists(dst_dir):
        if not overwrite:
            raise SystemExit("refusing to overwrite existing case dir %s "
                             "(pass --overwrite)" % dst_dir)
        shutil.rmtree(dst_dir)
    shutil.copytree(src_dir, dst_dir)
    # never carry stale results into a new case
    for junk in ("run.log", "1.rtt", "1.res", "1.resb", "1.flavia.res",
                 "1.flavia.msh", "1.gpv", "1.chk", "1.act", "1.stf"):
        p = os.path.join(dst_dir, junk)
        if os.path.exists(p):
            os.remove(p)
    return dst_dir


def write_records(path, records):
    """Write a whole free-format HSTAR file as a list of records."""
    with open(path, "w") as fh:
        for r in records:
            fh.write(r.rstrip() + "\n")
    return path


def _selftest():
    assert read_tokens("  1  2  3*0.0  ") == ["1", "2", "0.0", "0.0", "0.0"]
    assert read_tokens("10*0") == ["0"] * 10
    assert read_tokens("2 9 0 0 1 0 0.000E+00 0")[-2] == "0.000E+00"
    assert read_tokens("3*1.0e-05") == ["1.0e-05"] * 3
    import tempfile
    d = tempfile.mkdtemp()
    p = os.path.join(d, "t.glb")
    open(p, "w").write("NPOIN npoinb NELEM\n  81  81  64\nvalv1\n")
    g = GlbFile(p)
    assert g.tokens_after("NPOIN") == ["81", "81", "64"]
    g.set_field_after("NPOIN", 0, 42)
    g.set_field_after("NPOIN", 2, 20)
    g.save()
    assert GlbFile(p).tokens_after("NPOIN") == ["42", "81", "20"]
    print("hstar_io selftest OK")


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        _selftest()
    else:
        print(__doc__)
