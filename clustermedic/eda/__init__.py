"""EDA triage: the ClusterMedic agent pattern applied to chip-design flow output.

evidence (parse STA/DRC/Yosys/flow logs) -> retrieve EDA runbooks -> grounded diagnosis
-> recommended fixes. Read-only: it never edits RTL, constraints or flow settings.
"""
