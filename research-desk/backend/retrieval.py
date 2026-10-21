"""LlamaIndex retriever with BM25 + Chroma local embeddings and rank fusion."""

import re
import threading
from functools import lru_cache
import chromadb
from chromadb.config import Settings
from rank_bm25 import BM25Okapi
from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import TextNode, NodeWithScore
from .store import RUNTIME
from .model import EMBED_MODEL
from . import model as llm
from .corpus import digest

LOCK = threading.Lock()


def tokens(text):
    return re.findall(r"[a-z0-9]+", text.lower())


def passage(pack):
    lines = [pack["company"], pack["report"], pack["notes"]]
    lines += [
        f"FY{c['period']} | {c['label']} | {c['value']} | {c['unit']} | {c['id']}"
        for c in pack["cells"]
    ]
    return "\n".join(lines)


@lru_cache(maxsize=1)
def client():
    return chromadb.PersistentClient(
        path=str(RUNTIME / "chroma"), settings=Settings(anonymized_telemetry=False)
    )


class FinancialRetriever(BaseRetriever):
    def __init__(self, documents, semantic=True):
        super().__init__()
        self.documents = documents
        self.semantic = semantic
        self.details = {}

    def _retrieve(self, query_bundle):
        if not self.documents:
            return []
        query = query_bundle.query_str
        texts = [passage(p) for p in self.documents]
        bm = BM25Okapi([tokens(t) for t in texts])
        sparse = sorted(
            range(len(texts)),
            key=lambda i: float(bm.get_scores(tokens(query))[i]),
            reverse=True,
        )
        rankings = [sparse]
        dense_error = None
        if self.semantic:
            try:
                with LOCK:
                    collection = client().get_or_create_collection(
                        "financial-evidence-hackathon",
                        metadata={"hnsw:space": "cosine"},
                    )
                    ids = [digest({"text": t, "model": EMBED_MODEL}) for t in texts]
                    present = set(collection.get(ids=ids)["ids"])
                    missing = [i for i, k in enumerate(ids) if k not in present]
                    if missing:
                        vectors = llm.embed(
                            ["search_document: " + texts[i] for i in missing]
                        )
                        collection.upsert(
                            ids=[ids[i] for i in missing],
                            embeddings=vectors,
                            documents=[texts[i] for i in missing],
                            metadatas=[
                                {
                                    "company": self.documents[i]["company"],
                                    "split": self.documents[i]["split"],
                                    "evidence_id": ids[i],
                                }
                                for i in missing
                            ],
                        )
                    vector = llm.embed(["search_query: " + query])[0]
                    response = collection.query(
                        query_embeddings=[vector],
                        n_results=len(ids),
                        where={"evidence_id": {"$in": ids}},
                    )
                    rankings.append([ids.index(k) for k in response["ids"][0]])
            except Exception as exc:
                dense_error = (
                    f"{type(exc).__name__}: semantic retrieval unavailable; BM25 used"
                )
        scores = {
            i: sum(
                1 / (60 + ranking.index(i) + 1) for ranking in rankings if i in ranking
            )
            for i in range(len(texts))
        }
        ordered = sorted(scores, key=scores.get, reverse=True)
        self.details = {
            "strategy": "hybrid_rrf" if len(rankings) == 2 else "bm25",
            "embedding_model": EMBED_MODEL if len(rankings) == 2 else None,
            "qualification": dense_error,
            "candidates": len(texts),
            "ranked_reports": [self.documents[i]["id"] for i in ordered],
        }
        return [
            NodeWithScore(
                node=TextNode(
                    id_=self.documents[i]["id"],
                    text=texts[i],
                    metadata={
                        "company": self.documents[i]["company"],
                        "report": self.documents[i]["report"],
                    },
                ),
                score=scores[i],
            )
            for i in ordered
        ]


def retrieve(query, documents, semantic=True):
    retriever = FinancialRetriever(documents, semantic)
    nodes = retriever.retrieve(query)
    lookup = {p["id"]: p for p in documents}
    return [lookup[n.node.node_id] for n in nodes], retriever.details
