"""Compare BM25 with a one-hop link expansion on the local CSE_421 corpus."""

import argparse
import re
from collections import defaultdict
from pathlib import Path, PurePosixPath

from knowledge_assistant.retrieval import search_lexical
from knowledge_assistant.storage import SQLiteDocumentStore
from scripts.evaluate_retrieval import CASES

DIVIDE = "Divide and Conquer Algorithm/Divide and Conquer.md"
CLOSEST = "Divide and Conquer Algorithm/Euclidean Closest Pair.md"
TRAVERSAL = "Graphs/Graph Traversal.md"
BIPARTITE = "Graphs/Bipartite Testing.md"
APPROXIMATION = "Greedy Algorithm/Greedy Graph Approximation Algorithms.md"

LINKED_CASES = (
    (
        "How do the three recursive stages apply to finding the nearest pair in two dimensions?",
        ((DIVIDE, ()), (CLOSEST, ("Second Try",))),
    ),
    (
        "What does combining recursive answers mean when points lie across the median line?",
        ((DIVIDE, ()), (CLOSEST, ("Second Try",))),
    ),
    (
        "Which traversals discover connected components, and how do you test every component for two-colorability?",
        ((TRAVERSAL, ("Algorithms",)), (BIPARTITE, ("Algorithm",))),
    ),
    (
        "How does a DFS back edge hint at an odd cycle, and why does an odd cycle rule out two colors?",
        ((TRAVERSAL, ("Algorithms",)), (BIPARTITE, ("Proof",))),
    ),
    (
        "What does it mean for a maximum cut to cross every edge, and what condition on the two vertex sets makes that possible?",
        ((APPROXIMATION, ("Maximizing Bipartiteness",)), (BIPARTITE, ())),
    ),
    (
        "How can a layer coloring decide if the maximum cut contains all edges?",
        ((APPROXIMATION, ("Maximizing Bipartiteness",)), (BIPARTITE, ("Algorithm",))),
    ),
)
BFS = "CSE_332/Graphs/Breadth-First Search.md"
DFS = "CSE_332/Graphs/Depth First Search.md"
SPANNING = "CSE_332/Graphs/Spanning Tree.md"
MST = "Greedy Algorithm/Greedy MST Algorithms.md"
CROSS_COURSE_CASES = (
    (
        "Which traversal finds shortest paths in an unweighted graph, and how does its queue track the distance from the source?",
        (
            (TRAVERSAL, ("Algorithms",)),
            (BFS, ("Shortest Path", "BFS with layers (distance)")),
        ),
    ),
    (
        "Which traversal finds reachable vertices and connected components, and how do layer numbers advance as neighbors are visited?",
        (
            (TRAVERSAL, ("Algorithms",)),
            (BFS, ("Shortest Path", "BFS with layers (distance)")),
        ),
    ),
    (
        "Which traversal can detect a cycle using a back edge, and what visited state identifies that edge?",
        ((TRAVERSAL, ("Algorithms",)), (DFS, ("Finding Cycles", "Back Edge"))),
    ),
    (
        "What distinguishes the edge choices of Prim and Kruskal, and how many edges are in the tree they produce?",
        ((MST, ("Rules:",)), (SPANNING, ())),
    ),
    (
        "Why can Prim select an edge to an unvisited vertex, and how does a priority queue implement its update differently from Dijkstra?",
        ((MST, ("Rules:",)), (SPANNING, ("Minimum Spanning Tree", "Prim's Algorithm"))),
    ),
)
WIKILINK = re.compile(r"(?<![!\\])\[\[([^\[\]\n]+)\]\]")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("--cross-course", action="store_true")
    args = parser.parse_args()
    if not args.database.is_file():
        parser.error("database does not exist")

    store = SQLiteDocumentStore(args.database)
    documents = store.list_documents()
    chunks = {chunk.id: (doc, chunk) for doc in documents for chunk in doc.chunks}
    labels = defaultdict(set)
    paths_by_title = defaultdict(set)
    for doc in documents:
        paths_by_title[PurePosixPath(doc.path).stem.casefold()].add(doc.path)
        for chunk in doc.chunks:
            labels[doc.path, chunk.heading].add(chunk.id)

    controls = tuple((query, ((path, heading),)) for query, path, heading in CASES)
    groups = [("Linked", LINKED_CASES), ("Control", controls)]
    if args.cross_course:
        groups.append(("Cross-course", CROSS_COURSE_CASES))
    print(f"{len(documents)} notes, {len(chunks)} passages")
    for name, cases in groups:
        baseline_hits = expanded_hits = 0
        for number, (query, expected) in enumerate(cases, start=1):
            targets = [labels[label] for label in expected]
            if not all(targets):
                parser.error(f"missing label for {query}")
            ranked = search_lexical(store, query, limit=len(chunks))
            baseline = ranked[:5]
            linked_paths = set()
            for chunk_id in baseline[:3]:
                doc, chunk = chunks[chunk_id]
                for match in WIKILINK.finditer(chunk.text):
                    title = match[1].split("|", 1)[0].split("#", 1)[0].strip()
                    paths = paths_by_title[title.casefold()]
                    if len(paths) == 1:
                        linked_paths.update(paths - {doc.path})

            # Reserve only the last slot for the strongest BM25 match in linked notes.
            candidate = next(
                (item for item in ranked if chunks[item][0].path in linked_paths), None
            )
            expanded = (
                (*baseline[:4], candidate)
                if candidate is not None and candidate not in baseline
                else baseline
            )
            baseline_coverage = sum(bool(ids.intersection(baseline)) for ids in targets)
            expanded_coverage = sum(bool(ids.intersection(expanded)) for ids in targets)
            baseline_hits += baseline_coverage == len(targets)
            expanded_hits += expanded_coverage == len(targets)
            print(
                f"{name} {number}: {baseline_coverage}/{len(targets)} -> "
                f"{expanded_coverage}/{len(targets)} | changed={baseline != expanded}"
            )
            if baseline != expanded:
                for label, item in (("added", candidate), ("removed", baseline[4])):
                    doc, chunk = chunks[item]
                    print(f"  {label}: {doc.path} / {chunk.heading}")
        print(
            f"{name} full coverage: {baseline_hits}/{len(cases)} -> "
            f"{expanded_hits}/{len(cases)}"
        )


if __name__ == "__main__":
    main()
