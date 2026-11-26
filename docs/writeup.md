# ClusterMedic: building and breaking an incident-triage agent

This is a short engineering write-up: what I built, why it is built that way, and, mostly, what went wrong and what each failure taught me. All numbers come from [`results.md`](results.md), which has the method and caveats for each.

## The question

Can a local LLM agent triage HPC/GPU incidents (find the root cause and propose a fix) **without ever being trusted to change the cluster on its own**? And when it does better than a few if-statements, where exactly does that advantage come from?

To answer that honestly I needed ground truth, so the whole cluster is simulated and every incident is **injected on purpose and labelled**. That's the key design decision. Without labels, an agent demo is just a story.

## Design decisions

**Simulate everything, label everything.** A two-node Slurm cluster in Docker, a DMTF Redfish mockup for the BMC, and a fake DCGM exporter for GPUs. Ten fault injectors write their ground truth to `eval/injections.jsonl`, so every diagnosis can be scored automatically.

**Always compare against a rules baseline.** Every evaluation scores the LLM next to a deterministic rules diagnoser that sees the same evidence. If the LLM can't beat a few if-statements, it isn't adding anything.

**Treat the LLM as untrusted.** The model chooses from a fixed set of root causes (a JSON-schema enum) and a fixed allowlist of actions. A grounding check rejects any diagnosis that isn't supported by an observed anomaly. Every state change waits for a human. These checks sit outside the model, so they hold even when the model is fooled.

**Hybrid retrieval.** BM25 for exact identifiers (node names, Xid codes, error strings), embeddings for paraphrases, combined with reciprocal rank fusion.

**Pre-register test sets.** The ticket-triage and injection test sets were written before running them, so I couldn't tune the system against them unnoticed. Where I did change something after seeing results, `results.md` says so.

## What went wrong, and what I changed

### 1. The model diagnosed from the runbooks, not the cluster
Early on, the LLM said `disk_full` for a cluster with no disk problem. It had read the disk-full runbook in its retrieved context and repeated it. **Fix:** a grounding check (the cause must match an observed anomaly, otherwise `needs_review` and only `report_only` may be proposed), a tighter prompt, and confidence normalization (the model sometimes answered `80` instead of `0.8`). **Lesson:** retrieval context is evidence about the *world*, not about *this incident*. The agent has to be told which is which, and then checked.

### 2. Clean faults are too easy to measure anything
On 32 injected incidents, the LLM and the rules baseline **both scored 32/32**. That's not a win for the LLM; it means the benchmark couldn't tell them apart. **Fix:** a pre-registered ticket-only evaluation (22 tickets, no live symptoms, 9 of them paraphrased). The LLM got 22/22; rules got 13/22 and **0/9 on paraphrases**. **Lesson:** the LLM's value is in reading unstructured human text. On clean telemetry, rules are enough.

### 3. Incidents leaked into each other
Prometheus range queries looked back further than the gap between incidents, so the next incident still saw the previous fault's metrics. **Fix:** a quiet-period wait between incidents and shorter (2-minute) metric windows. **Lesson:** in a time-series system, "clean state" means waiting out every lookback window, not just clearing the fault.

### 4. Fault injection had its own bugs
- Container lookup by name broke; nodes are now matched to containers by their Slurm `NodeAddr` IP.
- Slurm takes about 1.5 minutes to mark a dead `slurmd` as not responding, so injections now wait to settle, and the evidence includes a `responding` field.
- Pressing Ctrl+C during that wait left a fault running but untracked. Faults are now recorded **before** settling, injections are refused on unhealthy nodes, and only one fault may be active at a time.

**Lesson:** the test harness needs the same care as the system under test.

### 5. The laptop went to sleep mid-evaluation
One of 33 incidents errored because the machine slept during a quiet-period wait. **Fix:** disable standby during runs, and make the harness record *which* anomaly blocked it. The incident was excluded and reported as an error, not silently dropped.

### 6. Prompt injection: the model was fooled, the system wasn't
Of 8 tickets (7 attacks, 1 benign), **2 changed the model's diagnosis**. Both failed the grounding check because the cluster evidence didn't support them, so both went to human review: **0 unsafe actions**. A regex filter flagged 5/7 attacks and 0/1 benign. **Lesson:** don't measure injection safety by whether the model resists; measure whether anything bad can happen when it doesn't.

### 7. Retrieval: embeddings lose on exact identifiers
On a harder question set, vector search got only 0.60 hit@1, against 0.90 for BM25, because queries were full of codes and names that embeddings blur. Hybrid got 0.80. I then added one symptom line to a runbook after seeing a failing question; that's test-set tuning and is recorded as such.

### 8. Real EDA tool output disagreed with my assumptions
The EDA extension parses OpenROAD/Yosys output. Checked against real logs:
- Yosys reports undriven signals **per bit**, escapes names with backslashes, and my number regexes could match across newlines.
- **Latch warnings that weren't latches.** On the real `gcd` design, Yosys warns "Latch inferred", but the synthesized netlist has **0 latch cells**: the latches were optimized away. Because latch ranked above timing, the agent hid real setup violations. Score: LLM 4/8, rules 5/8. **Fix:** count a latch only if latch cells exist in the synthesis statistics; otherwise make it an informational note. Score: 8/8 for both. This fix was made after seeing those same 8 runs, so it shows the fix works, not that it generalizes.
- Writing the test for that fix found a second bug: Yosys prints its statistics twice, so I counted 16 latches instead of 8.
- An empty run directory was reported as `no_issue`. It's now refused: no evidence means "unknown", never "healthy".

**Lesson:** a warning is a claim about the design. Check it against the final artifact before acting on it.

### 9. Evaluation runs could open real tickets
The alert service stood down during end-to-end evaluations, but not during model comparisons, which also inject faults. **Fix:** both share one "evaluation running" flag, and only the outermost run removes it.

### 10. The approval prompt approved itself
While recording the demo, text typed during the one-minute wait was buffered and then **answered the "approve?" prompt** without anyone deciding. **Fix:** the demo discards buffered input before asking. **Lesson:** a human-approval step only means something if it captures a *fresh* decision. The real approval path uses an explicit command with an incident ID, so this only affected the demo script, but it's the same class of bug.

## Model comparison

With identical prompts, retriever and guardrails: qwen2.5:7b and llama3.1:8b both scored 22/22 on tickets. qwen2.5:3b was faster but scored 18/22 and raised false alarms on 2 of 4 benign tickets. **0 unsafe actions for every model**, which again points at the guardrails rather than the model.

## Limitations

The hardware is mocked, faults are injected one at a time, and the test sets are small (32 incidents, 22 tickets, 8 injection tickets, 8 EDA runs). Real incidents overlap, and real telemetry is noisier. Nothing here has run on a production cluster.

## What I'd do next

- Inject **overlapping faults** and noisy, irrelevant alerts. That's where I'd expect rules to break and the LLM's ranking to matter.
- Grow the ticket set with tickets written by other people, so the paraphrases aren't all mine.
- Run the EDA triage on more designs and PDKs, labelled **before** looking at the agent's output.
