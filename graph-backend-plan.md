 # Graph Intelligence Backend Plan

  ## Summary

  Build a FastAPI + Neo4j backend using Docker Compose. Neo4j is the single graph system of record; analytics use Neo4j GDS projections.
  Start with a repeatable synthetic investigation dataset combining cyber-fraud, laundering, and organized-crime patterns.

  ## Implementation Changes

  - Define a canonical graph model:
      - Typed canonical entities: Person, Phone, Account, Device, Vehicle, Location, Organization, and Case.
      - Immutable Evidence records for each source observation, retaining source ID, timestamp, confidence, ingest metadata, and source
        payload reference.

      - Derived weighted entity-to-entity relationships for fast traversal and analytics; each is traceable back to supporting evidence
        IDs.

      - Case membership and global entity identity; APIs support both case-scoped and explicitly global queries.

  - Add Neo4j constraints/indexes for stable entity IDs, case IDs, evidence IDs, normalized identifiers, and common search fields.
    Maintain graph-version metadata so cached analytics can be identified with the data version used.

  - Create synchronous, idempotent ingestion endpoints for versioned CSV/JSON contracts covering CDRs, transactions, and investigation/
    association records. Normalize records into the common entity/evidence schema before graph writes.

  - Implement deterministic entity resolution:
      - Automatically resolve exact high-confidence identifiers such as normalized phones, accounts, and device IDs.
      - Put fuzzy or conflicting identity matches into a review queue; do not merge them automatically.

  - Expose investigator APIs for entity search/details, scoped graph neighborhoods, evidence retrieval, centrality rankings, community
    detection, and weighted connection paths. All analytical responses include supporting entity/edge/evidence data and template-
    generated explanations.

  - Run centrality, Louvain communities, and weighted paths synchronously for the seeded MVP dataset, storing analysis-run metadata and
    returning clear limits/errors for oversized requests.

  - Add a future-NL safe query contract: a typed, validated intent request (find_entity, neighbors, connection_path, rank_influencers,
      - Do not accept or execute LLM-produced Cypher.
      - Keep the local/self-hosted LLM outside v1; it will later translate NL into this contract and receive only structured, evidence-
        backed results.

  - Keep authentication out of the initial demo while adding ownership/team and audit-ready fields so JWT role enforcement can be
    introduced without reshaping the graph.

  ## Test Plan

  - Verify database constraints, indexes, repeatable schema initialization, and Docker startup.
  - Import the synthetic fixture twice and confirm idempotent entity/evidence/link counts.
  - Cover deterministic resolution, review-queue creation, and approved/rejected merge handling.
  - Validate path, centrality, and community results against known fixture topology and ensure every returned finding has evidence
    references.

  - Test API validation, case/global filtering, pagination, empty results, malformed imports, and unsupported query intents.
  - Confirm the query-contract endpoint rejects arbitrary Cypher, mutation-like inputs, unknown properties, and invalid identifiers.

  ## Recommended Follow-up Features

  - Temporal graph filters and “why is this link suspicious?” evidence timelines.
  - Saved investigator queries/watchlists and deterministic alert rules.
  - Confidence/risk scoring that distinguishes observed facts from derived inferences.
  - Audit logging and case-level access control before non-synthetic data is introduced.

  ## Assumptions

  - Local Docker Neo4j Community with the GDS plugin is the initial deployment target.
  - FastAPI is the backend framework.
  - The initial graph is global by default, with case-scoped queries available where needed.
  - Synthetic fixtures span all three requested domains, anchored around a cyber-fraud ring.
  - Imports and analytics are synchronous only for the MVP dataset; job-based execution is the planned scaling path.