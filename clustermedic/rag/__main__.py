"""CLI: python -m clustermedic.rag {index,query,eval}"""
import argparse
import json

from .evaluate import evaluate
from .store import BM25Retriever, VectorRetriever, build_index


def _retriever(kind: str):
    if kind == "bm25":
        return BM25Retriever()
    from .embed import OllamaEmbedder
    return VectorRetriever(OllamaEmbedder())


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m clustermedic.rag")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("index")
    q = sub.add_parser("query")
    q.add_argument("text")
    q.add_argument("-k", type=int, default=3)
    q.add_argument("--retriever", choices=["vector", "bm25"], default="vector")
    e = sub.add_parser("eval")
    e.add_argument("--retriever", choices=["vector", "bm25", "both"], default="both")
    a = p.parse_args(argv)

    if a.cmd == "index":
        from .embed import OllamaEmbedder
        print(f"indexed {build_index(OllamaEmbedder())} chunks")
    elif a.cmd == "query":
        for r in _retriever(a.retriever).search(a.text, k=a.k):
            print(f"{r['score']:>8}  {r['id']}")
    else:
        kinds = ["bm25", "vector"] if a.retriever == "both" else [a.retriever]
        for kind in kinds:
            res = evaluate(_retriever(kind))
            print(f"{kind:>6}: n={res['n']}  hit@1={res['hit@1']:.2f}  "
                  f"hit@3={res['hit@3']:.2f}  MRR={res['mrr']:.3f}")
            for m in res["misses"]:
                print(f"        miss (rank {m['rank']}): expected {m['expected']} :: {m['question']}")


if __name__ == "__main__":
    main()
