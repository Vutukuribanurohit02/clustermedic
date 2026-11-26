"""Collect evidence from a flow run directory (ORFS logs/ and reports/, or any folder of
.rpt/.log files) and turn it into plain-English anomaly lines."""
from pathlib import Path

from . import parsers

_STAGE_ORDER = ["synth", "1_", "2_", "3_", "4_", "5_", "6_", "final", "finish"]


def _files(run: Path, suffixes=(".rpt", ".log", ".txt")) -> list[Path]:
    return sorted(p for p in Path(run).rglob("*") if p.is_file() and p.suffix in suffixes)


def _stage_rank(p: Path) -> int:
    name = p.name.lower()
    return max((i for i, s in enumerate(_STAGE_ORDER) if s in name), default=-1)


def gather(run: Path) -> dict:
    files = _files(run)
    text = {p: p.read_text(errors="replace") for p in files}
    sta_files = [p for p in files if "Startpoint:" in text[p]]
    # Use the latest flow stage that has timing paths (e.g. 6_finish over 4_cts).
    final_sta = max(sta_files, key=_stage_rank) if sta_files else None
    paths = parsers.parse_sta_paths(text[final_sta]) if final_sta else []
    summary = {}
    for p in sorted(files, key=_stage_rank):
        summary.update(parsers.parse_slack_summary(text[p]))
    drc_files = [p for p in files if "drc" in p.name.lower() or "violation type:" in text[p]]
    drc = {"total": 0, "by_type": {}, "by_layer": {}}
    for p in drc_files:
        d = parsers.parse_drc(text[p])
        if d["total"] >= drc["total"]:
            drc = d
    yosys_files = [p for p in files if "yosys" in p.name.lower() or "Yosys" in text[p][:2000]]
    yosys = {"latches": [], "undriven": [], "multiple_drivers": []}
    for p in yosys_files:
        for k, v in parsers.parse_yosys(text[p]).items():
            yosys[k] = sorted(set(yosys[k]) | set(v))
    # A latch warning only matters if latch cells survive into the netlist. ORFS writes the
    # statistics to synth_stat.txt; standalone Yosys runs print them in the log (`stat`).
    stat_files = [p for p in files if "synth_stat" in p.name] or yosys_files
    counts = [c for c in (parsers.parse_latch_cells(text[p]) for p in stat_files) if c is not None]
    yosys["latch_cells"] = max(counts) if counts else None
    errors = []
    for p in files:
        for e in parsers.parse_flow_errors(text[p]):
            if e not in errors:
                errors.append({**e, "file": p.name})
    return {"run": str(run), "files": [p.name for p in files],
            "sta_source": final_sta.name if final_sta else None, "paths": paths,
            "slack_summary": summary, "drc": drc, "yosys": yosys, "errors": errors}


def anomalies(ev: dict) -> list[str]:
    out = []
    for e in ev["errors"]:
        out.append(f"flow error [{e['code']}] in {e['file']}: {e['message'][:160]}")
    y = ev["yosys"]
    for s in y["multiple_drivers"]:
        out.append(f"synthesis: multiple conflicting drivers for {s}")
    for s in y["undriven"]:
        out.append(f"synthesis: wire {s} is used but has no driver")
    if y["latches"]:
        if y.get("latch_cells") == 0:
            # informational only: deliberately does not match the latch rule
            out.append(f"note: Yosys warned about possible latches ({', '.join(y['latches'][:3])}) "
                       "but 0 latch cells remain in the synthesized netlist (optimized away)")
        else:
            cells = (f" ({y['latch_cells']} latch cells in netlist)" if y.get("latch_cells")
                     else " (no cell statistics found to confirm)")
            for s in y["latches"]:
                out.append(f"synthesis: latch inferred for signal {s}{cells}")
    viol = [p for p in ev["paths"] if p["violated"]]
    for kind, label in (("max", "setup"), ("min", "hold")):
        vs = sorted((p for p in viol if p["path_type"] == kind), key=lambda p: p["slack"])
        if vs:
            w = vs[0]
            extra = []
            if w["logic_levels"]:
                extra.append(f"{w['logic_levels']} logic levels")
            if w["max_fanout"]:
                extra.append(f"max fanout {w['max_fanout']}")
            out.append(f"{label} timing violated: worst slack {w['slack']:.3f} ns, "
                       f"{w['startpoint']} -> {w['endpoint']} (group {w['path_group']}"
                       f"{', ' + ', '.join(extra) if extra else ''}); {len(vs)} violating path(s) reported")
    s = ev["slack_summary"]
    if not viol and s.get("wns", 0) < 0:
        out.append(f"setup timing violated: wns {s['wns']} ns, tns {s.get('tns')} ns")
    d = ev["drc"]
    if d["total"]:
        top = ", ".join(f"{n} {t}" for t, n in sorted(d["by_type"].items(), key=lambda x: -x[1])[:3])
        layers = ", ".join(sorted(d["by_layer"], key=lambda k: -d["by_layer"][k])[:3])
        out.append(f"DRC: {d['total']} violations after routing ({top or 'types not listed'})"
                   f"{'; layers ' + layers if layers else ''}")
    return out
