"""Parsers for OpenROAD/OpenSTA (and PrimeTime-style) timing reports, TritonRoute DRC reports,
Yosys logs and flow error lines. Pure functions over text, so they are unit-testable."""
import re

_FLOP = re.compile(r"df|dl[xr]|latch|sdf|edf", re.I)
_CLOCK_CELL = re.compile(r"clkbuf|clkinv|clkdlybuf|clkbufkapwr", re.I)
_PIN = re.compile(r"\s(?P<inst>[^\s/()]+)/(?P<pin>[A-Za-z0-9_\[\]]+)\s+\((?P<cell>[^)]+)\)")
_NET_FANOUT = re.compile(r"^\s*(\d+)\s+[\d.]+\s+.*\(net\)", re.M)


def _num(pattern: str, text: str):
    m = re.search(pattern, text, re.M)
    return float(m.group(1)) if m else None


def parse_sta_paths(text: str) -> list[dict]:
    """Every timing path block (from 'Startpoint:' to its slack line)."""
    paths = []
    for block in re.split(r"(?=^\s*Startpoint:)", text, flags=re.M)[1:]:
        start = re.search(r"Startpoint:\s*(\S+)(?:\s*\((.*?)\))?", block)
        end = re.search(r"Endpoint:\s*(\S+)(?:\s*\((.*?)\))?", block)
        slack = re.search(r"(-?\d+\.\d+)[ \t]+slack[ \t]+\((VIOLATED|MET)", block) or \
            re.search(r"slack[ \t]+\((VIOLATED|MET)[^)]*\)[ \t]+(-?\d+\.\d+)", block)
        if not (start and end and slack):
            continue
        if slack.re.pattern.startswith("(-?"):
            slack_v, status = float(slack.group(1)), slack.group(2)
        else:
            status, slack_v = slack.group(1), float(slack.group(2))
        data_part = block.split("data arrival time")[0]
        insts, cells = [], {}
        for m in _PIN.finditer(data_part):
            if m["inst"] not in cells:
                insts.append(m["inst"])
                cells[m["inst"]] = m["cell"]
        logic = [i for i in insts if not _FLOP.search(cells[i]) and not _CLOCK_CELL.search(cells[i])]
        fanouts = [int(f) for f in _NET_FANOUT.findall(data_part)]
        paths.append({
            "startpoint": start.group(1), "endpoint": end.group(1),
            "path_group": (re.search(r"Path Group:\s*(\S+)", block) or [None, None])[1],
            "path_type": (re.search(r"Path Type:\s*(max|min)", block) or [None, "max"])[1],
            "slack": slack_v, "violated": status == "VIOLATED",
            "arrival": _num(r"(-?\d+\.\d+)[ \t]+data arrival time", block)
            or _num(r"data arrival time[ \t]+(-?\d+\.\d+)", block),
            "required": _num(r"(-?\d+\.\d+)[ \t]+data required time", block)
            or _num(r"data required time[ \t]+(-?\d+\.\d+)", block),
            "logic_levels": len(logic),
            "max_fanout": max(fanouts) if fanouts else None,
            "weakest_cells": sorted({cells[i] for i in logic if re.search(r"_1$|X1\b|_0$", cells[i])})[:5],
        })
    return paths


def parse_slack_summary(text: str) -> dict:
    out = {}
    for key, pat in [("wns", r"^\s*wns(?:\s+max)?\s+(-?\d+\.?\d*)"),
                     ("tns", r"^\s*tns(?:\s+max)?\s+(-?\d+\.?\d*)"),
                     ("worst_slack", r"^\s*worst slack(?:\s+max)?\s+(-?\d+\.?\d*)")]:
        vals = re.findall(pat, text, re.M)
        if vals:
            out[key] = float(vals[-1])
    return out


def parse_drc(text: str) -> dict:
    """TritonRoute DRC report: counts by violation type and by layer."""
    by_type, by_layer = {}, {}
    for block in re.split(r"(?=^\s*violation type:)", text, flags=re.M)[1:]:
        vtype = re.search(r"violation type:\s*(.+)", block).group(1).strip()
        by_type[vtype] = by_type.get(vtype, 0) + 1
        layer = re.search(r"on Layer\s+(\S+)", block)
        if layer:
            by_layer[layer.group(1)] = by_layer.get(layer.group(1), 0) + 1
    total = sum(by_type.values())
    logged = re.findall(r"Number of violations\s*=\s*(\d+)", text)
    if not total and logged:
        total = int(logged[-1])
    return {"total": total, "by_type": by_type, "by_layer": by_layer}


def _clean(sig: str) -> str:
    """Yosys escapes names with backslashes (`\\top.\\q`); strip them and trailing colons."""
    return sig.replace("\\", "").rstrip(":'`")


def parse_yosys(text: str) -> dict:
    # Formats checked against real Yosys 0.7x output (see tests/fixtures/eda/yosys_*.log).
    latches = re.findall(r"Latch inferred for signal\s+`?([^'`\s]+)", text)
    # undriven warnings are per bit: "Wire top.\\mask [0] is used but has no driver."
    undriven = re.findall(r"Wire\s+(\S+?)(?:\s*\[\d+\])?\s+is used but has no driver", text)
    multi = re.findall(r"multiple conflicting drivers for\s+(\S+)", text, re.I)
    multi += re.findall(r"Driver-driver conflict for\s+(\S+)", text)
    return {"latches": sorted({_clean(x) for x in latches}),
            "undriven": sorted({_clean(x) for x in undriven}),
            "multiple_drivers": sorted({_clean(x) for x in multi})}


# Latch cells as they appear in Yosys `stat` output: generic ($_DLATCH_*) or sky130 (dlx*, dlr*).
# Excludes delay cells (dlygate, dlymetal) and integrated clock-gating cells (dlclkp), whose
# internal latch is intentional.
_LATCH_CELL = re.compile(r"(\$_DLATCH\w*|\bsky130_fd_sc_\w+?__dl[xr]\w*|\b\w*LATCH\w*_X\d+)")


def parse_latch_cells(text: str) -> int | None:
    """Total latch cells in synthesis statistics; None if the text has no cell statistics."""
    if not re.search(r"Number of cells|cells\b", text):
        return None
    # Statistics are often printed more than once (e.g. by `synth` and again by `stat`):
    # keep the last count per cell type instead of summing every occurrence.
    last = {}
    for line in text.splitlines():
        m = _LATCH_CELL.search(line)
        if m:
            nums = [int(n) for n in re.findall(r"(?<![\w.$])(\d+)(?![\w.])", _LATCH_CELL.sub(" ", line))]
            last[m.group(1)] = nums[0] if nums else 0
    return sum(last.values())


def parse_flow_errors(text: str) -> list[dict]:
    return [{"code": m.group(1), "message": m.group(2).strip()}
            for m in re.finditer(r"\[ERROR ([A-Z]+-\d+)\]\s*(.*)", text)]
