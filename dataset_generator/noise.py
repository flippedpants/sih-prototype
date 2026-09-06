"""
Background "legitimate" traffic generator (Phase C noise layer).

Produces an ordinary Barabasi-Albert social graph of Person+Account nodes
with regular, unremarkable transactions (no suspicious timing or
layering), plus a small number of deliberate cross-cluster
SHARED_ADDRESS/SHARED_DEVICE edges into the fraud rings - the false-positive
risk described in schema Sec. 3.4, needed so community detection has
something realistic to filter against.
"""

import random
from datetime import timedelta

import networkx as nx

from entities import make_account, make_person
from motifs import REFERENCE_DATE, make_transaction_edge


def generate_noise(num_nodes: int, num_cross_links: int, ring_person_ids=None) -> dict:
    """
    Builds num_nodes ordinary (non-fraud) Person+Account pairs connected by a
    Barabasi-Albert graph with plain transaction edges, then injects
    num_cross_links SHARED_ADDRESS/SHARED_DEVICE edges between noise people
    and ring_person_ids (if given).
    """
    nodes, edges = [], []

    if num_nodes <= 0:
        return {"nodes": nodes, "edges": edges}

    m = 2 if num_nodes > 2 else 1
    ba_graph = nx.barabasi_albert_graph(n=num_nodes, m=m)

    person_ids = []
    account_id_by_node = {}
    for graph_node in ba_graph.nodes():
        person = make_person(role="legitimate")
        account = make_account(person["id"])
        nodes += [person, account]
        person_ids.append(person["id"])
        account_id_by_node[graph_node] = account["id"]

    for u, v in ba_graph.edges():
        # regular, unremarkable pattern: modest amount, spread over the last
        # two years, ordinary retail channels only
        amount = random.uniform(200, 50_000)
        t = REFERENCE_DATE - timedelta(days=random.randint(1, 730), hours=random.randint(0, 23))
        channel = random.choice(["upi", "neft_imps"])
        edges.append(make_transaction_edge(account_id_by_node[u], account_id_by_node[v], amount, t, channel))

    if ring_person_ids:
        for _ in range(num_cross_links):
            noise_person = random.choice(person_ids)
            ring_person = random.choice(ring_person_ids)
            edges.append({
                "source_id": noise_person,
                "target_id": ring_person,
                "type": random.choice(["SHARED_ADDRESS", "SHARED_DEVICE"]),
                "confidence": round(random.uniform(0.3, 0.9), 2),
            })

    return {"nodes": nodes, "edges": edges}
