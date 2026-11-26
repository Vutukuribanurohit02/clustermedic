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
