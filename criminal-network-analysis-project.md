# AI-Powered Criminal Network Analysis System

**Smart India Hackathon 2026 — Project Documentation**

---

## 1. Problem Statement

Modern criminal activities are increasingly organized and interconnected, with criminals operating through networks of associates, intermediaries, financial channels, communication links, locations, and events. Law enforcement agencies collect large volumes of data — FIRs, Call Detail Records (CDRs), financial transaction records, surveillance reports, social media intelligence, criminal history databases — but this data is fragmented, unstructured, and distributed across multiple systems.

Manual link analysis makes it extremely difficult for investigators to identify:
- Key organizers/masterminds within a criminal network, as opposed to peripheral members
- Hidden or indirect connections between suspects who never interact directly but are linked through common associates
- Distinct criminal "rings" or clusters operating within a larger, noisy dataset
- The shortest and most relevant chain of connections between two persons of interest

Manual analysis is slow, error-prone, and doesn't scale — decentralized structures like mule-account rings, cyber-fraud syndicates, and trafficking networks often go undetected until late in an investigation, if at all.

---

## 2. Solution Overview

An AI/ML/graph-analytics system that ingests multi-source investigation data, automatically extracts entities and relationships, constructs a unified criminal network graph, and surfaces investigator-usable insights — key players, hidden clusters, connection paths, and suspicious patterns — through an interactive dashboard.

### Solution Objectives

- **Multi-source data collection & processing** — ingest FIRs, CDRs, financial records, surveillance reports, social media intel, criminal history, and intelligence reports, across structured and unstructured formats
- **Entity extraction** — apply NLP to extract people, locations, vehicles, phone numbers, and organizations from unstructured text
- **Relationship mapping** — build a unified graph combining explicit relational data (calls, transactions, shared addresses, case linkages) with NLP-derived links, and cluster the network into likely criminal rings
- **Key player identification** — surface influential individuals using graph centrality measures; find and explain the shortest, most significant path between any two individuals of interest
- **Suspicious pattern & anomaly detection** — detect indirect-linkage patterns (e.g., mule relationships — two individuals who never interact directly but consistently transact through a common third party)
- **Investigator-usable output** — interactive visual dashboard with auto-generated, plain-language case summaries, not just raw graph metrics

---

## 3. System Architecture

### 3.1 Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                          DATA SOURCES                                 │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌────────────────────┐ │
│  │   FIRs   │  │   CDRs   │  │ Financial │  │  Surveillance /     │ │
│  │ (text)   │  │ (CSV/    │  │ Records   │  │  Social Media Intel │ │
│  │          │  │  JSON)   │  │ (CSV/JSON)│  │  (text)             │ │
│  └────┬─────┘  └────┬─────┘  └─────┬─────┘  └──────────┬──────────┘ │
└───────┼─────────────┼──────────────┼───────────────────┼────────────┘
        │              │              │                    │
        ▼              ▼              ▼                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    PHASE 1 — DATA INGESTION LAYER                    │
│  ┌────────────────────────┐        ┌─────────────────────────────┐ │
│  │  Structured Ingestion   │        │   Unstructured Ingestion     │ │
│  │  - Normalization        │        │   - Fine-tuned spaCy NER     │ │
│  │  - Entity resolution /  │        │   - Entity extraction        │ │
│  │    deduplication        │        │     (PERSON, LOCATION,       │ │
│  │  - Fuzzy matching        │        │      VEHICLE, PHONE, ORG)    │ │
│  └────────────┬────────────┘        └──────────────┬────────────────┘ │
│               └───────────────┬───────────────────┘                   │
│                                ▼                                       │
│                  Common Entity/Relationship Schema                     │
│         Entity: {id, type, canonical_name, aliases[], source_docs[]}  │
│         Relationship: {source_id, target_id, type, weight,            │
│                         source_doc, timestamp}                         │
└─────────────────────────────────┬─────────────────────────────────────┘
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  PHASE 2 — GRAPH CONSTRUCTION                        │
│   NetworkX weighted, attributed graph                                │
│   Edge weight = frequency_score × recency_decay × amount_score       │
└─────────────────────────────────┬─────────────────────────────────────┘
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│               PHASE 3 — NETWORK ANALYSIS ENGINE                      │
│  ┌───────────────┐ ┌────────────────┐ ┌───────────────────────┐    │
│  │  Centrality    │ │   Community     │ │   Path Analysis        │    │
│  │  - Degree      │ │   Detection     │ │   - Shortest path      │    │
│  │  - Betweenness │ │   - Louvain     │ │   - Weighted path       │    │
│  │  - Eigenvector │ │     method      │ │     (relevance-based)   │    │
│  └───────────────┘ └────────────────┘ └───────────────────────┘    │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  Anomaly / Mule Detection — common-neighbor analysis          │    │
│  │  (Jaccard similarity / Adamic-Adar index)                     │    │
│  └─────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────┬─────────────────────────────────────┘
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    PHASE 4 — BACKEND & API                           │
│   FastAPI REST endpoints                                             │
│   /api/ingest   /api/centrality   /api/communities   /api/path       │
│   Deterministic graph queries — no LLM in the analysis path          │
│   Template-based plain-language explanation generator                │
│   (optional SLM paraphrasing layer on top of structured facts)       │
└─────────────────────────────────┬─────────────────────────────────────┘
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                 PHASE 5 — VISUALIZATION DASHBOARD                    │
│   Cytoscape.js / vis.js interactive graph rendering                  │
│   - Node search, cluster colour-coding                               │
│   - Click-to-inspect entity details                                  │
│   - Path-highlighting between selected suspects                      │
│   - Auto-generated case summaries                                    │
└─────────────────────────────────────────────────────────────────────┘

                    ┌─────────────────────────────┐
                    │   VALIDATION (cross-cutting)  │
                    │  - NER: synthetic Indian FIR   │
                    │    ground truth + real Indian  │
                    │    news-case text               │
                    │  - Graph algorithms: Montagna   │
                    │    Mafia, Caviar, Brazilian     │
                    │    Federal Police network,      │
                    │    manually-reconstructed        │
                    │    Indian case networks          │
                    └─────────────────────────────┘
```

### 3.2 Data Flow Summary

1. Structured data (CDRs, financial records) is normalized and deduplicated via entity resolution.
2. Unstructured data (FIRs, surveillance reports) is passed through a fine-tuned NER model to extract typed entities.
3. Both streams are unified into a common Entity/Relationship schema.
4. Entities and relationships are loaded into a NetworkX weighted graph.
5. The Network Analysis Engine computes centrality, communities, paths, and anomalies.
6. A FastAPI backend exposes deterministic graph-query endpoints — no generative model sits in the core analysis path.
7. The dashboard renders the graph interactively and surfaces plain-language explanations of findings.

---

## 4. Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| **NLP / Entity Extraction** | spaCy (fine-tuned), transformer-based NER (optional) | Extract PERSON, LOCATION, VEHICLE, PHONE, ORG from unstructured text |
| **Entity Resolution** | Fuzzy matching (Levenshtein / Jaro-Winkler), rule-based attribute matching | Deduplicate name/entity variants into canonical entities |
| **Graph Construction & Analysis** | NetworkX (Python) | Build weighted/attributed graph; run centrality, Louvain community detection, shortest-path, common-neighbor anomaly detection |
| **Backend API** | FastAPI | Expose deterministic REST endpoints for ingestion and graph queries |
| **Explanation Generation** | Template-based generator; optional small local LLM (Phi-3-mini / Llama-3.2-3B) for paraphrasing only | Convert structured graph facts into plain-language investigator summaries, without introducing hallucination risk |
| **Visualization** | Cytoscape.js or vis.js | Interactive network graph rendering, clustering, path highlighting |
| **Synthetic Data Generation** | Python (Barabási–Albert graph generation, template + LLM-assisted text generation) | Generate labeled training data and demo datasets grounded in real network structure research |
| **Validation Datasets** | Montagna Mafia, Caviar, Noordin Top, Brazilian Federal Police criminal intelligence network, Spain/Brazil corruption networks, manually reconstructed Indian case networks (from public news coverage) | Benchmark graph algorithms and NER extraction against real-world structure and text |

---

## 5. Implementation Plan by Phase

### Phase 1 — Data Ingestion & Graph Construction
- Ingest structured data (CDRs, financial logs, criminal history) as CSV/JSON
- Apply fine-tuned NER to unstructured text (FIRs, surveillance reports, social media intel)
- Normalize both streams into the common Entity/Relationship schema
- Construct a weighted, attributed NetworkX graph; edge weights combine interaction frequency, recency, and transaction amount

### Phase 2 — Network Analysis Engine
- **Centrality analysis**: degree, betweenness, eigenvector centrality to rank structural importance
- **Community detection**: Louvain method to identify criminal-ring-like clusters, filtered against relationship-type density to reduce false positives from innocent social/family clusters
- **Path analysis**: shortest-path and weighted-relevance path-finding between persons of interest
- **Anomaly detection**: common-neighbor analysis (Jaccard / Adamic-Adar) to flag indirect-linkage/mule patterns

### Phase 3 — Backend & API
- FastAPI REST endpoints for data ingestion and graph queries (centrality, communities, shortest path, cluster summaries)
- All core analysis endpoints are deterministic — no LLM in the critical path, to avoid hallucination risk in a law-enforcement context

### Phase 4 — Visualization Dashboard
- Interactive graph rendering (Cytoscape.js / vis.js) with node search, cluster colour-coding, click-to-inspect, path-highlighting
- Template-based auto-generated connection explanations (e.g., "X is linked to Y through 3 shared transactions with Z")

### Phase 5 — Validation
- **NER validation**: precision/recall/F1 on held-out synthetic Indian FIR text (ground truth by construction), plus qualitative testing against real Indian cyber-fraud/financial-crime case text drawn from public news coverage
- **Graph algorithm validation**: benchmark against real, published criminal network datasets —
  - Montagna Mafia (101 nodes / 256 edges, real 2007 investigation)
  - Caviar and Noordin Top networks
  - Brazilian Federal Police criminal intelligence network (23,666 nodes / 35,913 edges) — scalability stress test
  - Spain/Brazil political corruption networks — yearly-growth snapshots to validate evolving-network detection
  - Manually reconstructed networks from publicly reported Indian criminal cases (news coverage of cyber fraud rings, financial scams) — validates both NER and graph analysis against India-specific, real-world text and structure

---

## 6. Key Design Decisions & Rationale

- **NER strategy**: fine-tune spaCy on synthetic, template-generated Indian FIR text (labels generated automatically at construction time) rather than using IndicNER, since IndicNER targets native-script Indian languages, not English-medium FIR text with embedded Indian names.
- **Validation split**: NER is validated on India-specific text (synthetic + real news-derived); graph algorithms are validated on real criminal network topology regardless of geography, since structural patterns (hub-and-spoke, brokerage, clustering) generalize across criminal domains and countries.
- **No RAG/SLM in the core analysis path**: all centrality, community, and path queries are deterministic NetworkX computations exposed via FastAPI — avoids hallucination risk on real people's names in a law-enforcement context. An LLM/SLM is used only optionally, and only to paraphrase already-verified structured facts into natural language — never to generate new claims.
- **Edge weighting**: composite formula (log-scaled frequency × exponential recency decay × log-scaled amount) ensures centrality and community results are driven by meaningful signal rather than raw interaction counts.

---

## 7. Open Items / Future Enhancements

- Natural-language query interface (text-to-graph-query pattern) as a stretch goal, allowing investigators to ask questions in plain English
- GNN-based missing-link prediction for incomplete networks (stretch goal, differentiator beyond Louvain/centrality baseline)
- Cross-checking synthetic network structural statistics against published research on Indian mule-account/cyber-fraud network structure
