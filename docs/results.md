## Retrieval (2026-11-25, 20 hand-written questions, 10 runbooks, 60 chunks)
| Retriever | hit@1 | hit@3 | MRR |
|---|---|---|---|
| BM25 | 0.90 | 1.00 | 0.942 |
| Vector (nomic-embed-text, Chroma) | 0.95 | 1.00 | 0.975 |
Misses: BM25 failed on paraphrases (RB-001, RB-007); vector failed on an exact log string (RB-001).
Caveat: questions written alongside runbooks; small n.

## Hybrid RRF (2026-11-25)
```
question set: standard
  bm25: n=20  hit@1=0.90  hit@3=1.00  MRR=0.942
        miss (rank 3): expected RB-001 :: a node got taken out of service by someone for maintenance, how do I put it back?
        miss (rank 2): expected RB-007 :: double-bit ECC counter keeps increasing on one GPU
vector: n=20  hit@1=0.95  hit@3=1.00  MRR=0.975
        miss (rank 2): expected RB-001 :: sinfo shows c1 with state drain and reason Kill task failed, what should I check?
hybrid: n=20  hit@1=0.95  hit@3=1.00  MRR=0.967
        miss (rank 3): expected RB-001 :: a node got taken out of service by someone for maintenance, how do I put it back?
question set: hard
  bm25: n=10  hit@1=0.90  hit@3=0.90  MRR=0.900
        miss (rank None): expected RB-001 :: cancelled jobs never actually die on c2 and now the node is out of the pool
vector: n=10  hit@1=0.60  hit@3=0.90  MRR=0.775
        miss (rank 2): expected RB-004 :: node went idle* right after someone changed the time on it
        miss (rank 2): expected RB-008 :: Xid 74 keeps appearing in the kernel log on a multi-GPU node
        miss (rank 4): expected RB-001 :: cancelled jobs never actually die on c2 and now the node is out of the pool
        miss (rank 2): expected RB-006 :: fans look fine but the BMC says CPU1 is above its critical threshold
hybrid: n=10  hit@1=0.80  hit@3=0.90  MRR=0.867
        miss (rank 6): expected RB-001 :: cancelled jobs never actually die on c2 and now the node is out of the pool
        miss (rank 2): expected RB-006 :: fans look fine but the BMC says CPU1 is above its critical threshold
```

## Doc fix (2026-11-25): added user-reported symptom line to RB-001
Hard set after: BM25 1.00/1.00/1.000, Vector 0.70/1.00/0.850, Hybrid 0.90/1.00/0.950 (hit@1/hit@3/MRR).
Caveat: fix was made after seeing the failing question (test-set tuning). Need a held-out set in Week 5.

## Prompt injection (2026-11-25, fan_failure active, 8 tickets: 7 attacks + 1 benign, qwen2.5:7b)
- Diagnosis changed by ticket: 2/8 (both to no_fault; one polite social-engineering, one "maintenance mode").
- Both changed diagnoses were grounded=False -> needs_review -> report_only: 0 unsafe actions possible.
- Cost of the attack: fault left for human review instead of auto-proposed fix (availability, not safety).
- Regex injection filter: flagged 5/7 attacks, 0/1 benign.
## End-to-end evaluation (2026-11-26 03:41 UTC, model qwen2.5:7b, 3 per fault + 3 healthy controls, seed 7)
| Metric | Value |
|---|---|
| Incidents scored | 32 (errors: 1) |
| Diagnosis accuracy: LLM agent | 1.0 |
| Diagnosis accuracy: rules baseline | 1.0 |
| Correct action | 1.0 |
| Correct target | 1.0 |
| End-to-end correct (cause + action + target) | 1.0 |
| Flagged needs_review | 0.0 |
| Unsafe proposals (wrong state change offered unflagged) | 0 |
| Actions executed during dry run | 0 |
| Time to diagnosis, median (s, warm model) | 2.9 |

| Fault | n | LLM correct | Rules correct | End-to-end |
|---|---|---|---|---|
| cpu_overheat | 3 | 3 | 3 | 3 |
| fan_failure | 3 | 3 | 3 | 3 |
| gpu_ecc_dbe | 3 | 3 | 3 | 3 |
| gpu_off_bus | 2 | 2 | 2 | 2 |
| gpu_overheat | 3 | 3 | 3 | 3 |
| gpu_sbe_storm | 3 | 3 | 3 | 3 |
| healthy | 3 | 3 | 3 | 3 |
| jobs_pending | 3 | 3 | 3 | 3 |
| node_drain | 3 | 3 | 3 | 3 |
| nvlink_errors | 3 | 3 | 3 | 3 |
| slurmd_down | 3 | 3 | 3 | 3 |
Interpretation: every incident has one clean, unambiguous anomaly, so a keyword rules baseline
matches the LLM. 1 incident errored (laptop sleep stalled the quiet-wait), reported and excluded.
Next: a harder scenario set (compound faults, red herrings, misleading tickets) to test whether the
LLM adds value over rules.
## Ticket-only triage (pre-registered set, 22 tickets, model qwen2.5:7b)
| Ticket kind | n | LLM correct | Rules correct |
|---|---|---|---|
| literal | 9 | 9 | 9 |
| paraphrased | 9 | 9 | 0 |
| benign | 4 | 4 | 4 |
| **all** | 22 | 22 | 13 |

State-changing actions proposed: 0 (expected 0: ticket-only diagnoses are always needs_review -> report_only)
