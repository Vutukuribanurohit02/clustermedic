## Retrieval (2026-11-25, 20 hand-written questions, 10 runbooks, 60 chunks)
| Retriever | hit@1 | hit@3 | MRR |
|---|---|---|---|
| BM25 | 0.90 | 1.00 | 0.942 |
| Vector (nomic-embed-text, Chroma) | 0.95 | 1.00 | 0.975 |
Misses: BM25 failed on paraphrases (RB-001, RB-007); vector failed on an exact log string (RB-001).
Caveat: questions written alongside runbooks; small n.
