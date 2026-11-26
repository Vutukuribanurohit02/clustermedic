"""Fault injector: breaks the lab on purpose and records the true root cause.

The agent must never import this package. Ground truth is written to eval/injections.jsonl,
which the evaluation suite reads; the agent only sees the cluster.
"""
