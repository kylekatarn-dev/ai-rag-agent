# Knowledge Base Architecture

## Executive Summary

This document describes the knowledge base architecture for the Real Estate AI Assistant. The system uses a **hybrid RAG (Retrieval-Augmented Generation)** approach combining:

- **Vector embeddings** for semantic similarity search
- **BM25 keyword matching** for exact term matching
- **LLM reranking** for business-aware result ordering
- **Structured metadata filtering** for precise property matching

The knowledge base contains **4 main entities**: Property, Lead, Broker, and Conversation, with relationships enabling full lead lifecycle management from initial inquiry to broker handoff.

**Database Layer**: The system uses **SQLite** for persistent storage of relational data (leads, conversations, brokers) and **ChromaDB** as the vector database for semantic property search.

---

## Supported Regions

The system supports the following regions of the Czech Republic:

| Region | Areas | Example Locations |
|--------|-------|-------------------|
| **Praha** | Prague 1-10, Prague surroundings | Pankrac, Karlin, Smichov, Hostivice |
| **Stredni Cechy** | Central Bohemia | Mlada Boleslav, Kladno, Kolin |
| **Jizni Cechy** | South Bohemia | Ceske Budejovice, Tabor |
| **Zapadni Cechy** | West Bohemia (Plzen, Karlovy Vary) | Plzen, Karlovy Vary |
| **Severni Cechy** | North Bohemia (Usti, Liberec) | Usti nad Labem, Liberec |
| **Vychodni Cechy** | East Bohemia (Hradec, Pardubice) | Hradec Kralove, Pardubice |
| **Jizni Morava** | South Moravia | Brno, Znojmo |
| **Severni Morava** | North Moravia (Olomouc, Ostrava) | Ostrava, Olomouc |

---

## Entity Relationship Diagram

```
                                    +------------------------------------------+
                                    |              VECTOR STORE                |
                                    |              (ChromaDB)                  |
                                    |                                          |
                                    |  +------------------------------------+  |
                                    |  |     Property Embeddings            |  |
                                    |  |     (text-embedding-3-small)       |  |
                                    |  |                                    |  |
                                    |  |  - Semantic text representation    |  |
                                    |  |  - Metadata filters                |  |
                                    |  |  - Priority scores                 |  |
                                    |  +------------------------------------+  |
                                    +------------------+-------------------+---+
                                                       |
                              +------------------------+------------------------+
                              |                                                 |
                              v                                                 v
+-----------------------------------------+         +-----------------------------------------+
|            PROPERTY (Nemovitost)        |         |              LEAD (Klient)              |
+-----------------------------------------+         +-----------------------------------------+
| Core Attributes:                        |         | Identification:                         |
|  - id (int, PK)                         |         |  - id (UUID, PK)                        |
|  - property_type (warehouse|office)     |<------->|  - created_at (datetime)                |
|  - location (string)                    |   M:N   |                                         |
|  - location_region (string)             |  match  | Contact Info:                           |
|  - area_sqm (int)                       |         |  - name, email, phone, company          |
|  - price_czk_sqm (int)                  |         |                                         |
|  - availability (string|date)           |         | Requirements:                           |
|  - parking_spaces (int)                 |         |  - property_type (warehouse|office)     |
|  - amenities (list[string])             |         |  - min_area_sqm, max_area_sqm           |
|                                         |         |  - preferred_locations (list)           |
| Business Attributes:                    |         |  - preferred_regions (list)             |
|  - is_featured (bool)                   |         |  - max_price_czk_sqm                    |
|  - is_hot (bool)                        |         |  - move_in_urgency                      |
|  - priority_score (0-100)               |         |                                         |
|  - commission_rate (float)              |         | Qualification:                          |
|                                         |         |  - lead_score (0-100)                   |
| Computed Fields:                        |         |  - lead_quality (HOT|WARM|COLD)         |
|  - total_monthly_rent                   |         |  - customer_type                        |
|  - is_available_now                     |         |  - matched_properties (list[int])       |
|  - value_score                          |         |                                         |
|  - location_region (normalized)         |         | Status:                                 |
+-----------------------------------------+         |  - status (new->qualified->closed)      |
              |                                     |  - assigned_broker_id                   |
              |                                     |  - conversation_summary                 |
              | 1:N                                 +-----------------------------------------+
              | assigned                                           |
              v                                                    | 1:N
+-----------------------------------------+                        | owns
|            BROKER (Makler)              |                        v
+-----------------------------------------+         +-----------------------------------------+
|  - id (int, PK)                         |         |          CONVERSATION (Konverzace)      |
|  - name, email, phone                   |<--------|                                         |
|  - specialization (warehouse|office)    |   1:N   |  - lead (Lead ref)                      |
|  - regions (list[string])               |  handles|  - messages (list[Message])             |
|  - is_available (bool)                  |         |  - current_phase (enum)                 |
|  - current_leads_count                  |         |  - properties_shown (list[int])         |
|  - max_leads (capacity)                 |         |  - questions_asked (list[str])          |
+-----------------------------------------+         |  - created_at, updated_at               |
                                                    +-----------------------------------------+
```

---

## Database Architecture

```
+---------------------------+     +---------------------------+
|         SQLite            |     |        ChromaDB           |
|   (Relational Database)   |     |   (Vector Database)       |
+---------------------------+     +---------------------------+
|                           |     |                           |
|  Tables:                  |     |  Collections:             |
|  - leads                  |     |  - properties             |
|  - conversations          |     |                           |
|  - brokers                |     |  Stores:                  |
|  - messages               |     |  - Vector embeddings      |
|                           |     |  - Property metadata      |
|  Stores:                  |     |  - Document IDs           |
|  - Client contact info    |     |                           |
|  - Conversation history   |     |  Persistence:             |
|  - Lead scores and status |     |  - ./chroma_db            |
|  - Broker assignments     |     |                           |
|                           |     |                           |
|  File: ./data/app.db      |     |                           |
+---------------------------+     +---------------------------+

Implementation: app/persistence/database.py, app/persistence/repositories.py
```

---

## RAG Pipeline Architecture

```
+---------------------------------------------------------------------+
|                         RAG PIPELINE                                |
+---------------------------------------------------------------------+
|                                                                     |
|  1. USER QUERY (Czech natural language)                             |
|     |                                                               |
|     v                                                               |
|  2. QUERY EXPANSION                                                 |
|     - Czech synonyms (sklad -> warehouse, skladiste, hala)          |
|     - Location variants (Praha -> Praha 1-10, around Prague)        |
|     - Region detection (Brno -> Jizni Morava)                       |
|     |                                                               |
|     v                                                               |
|  3. HYBRID SEARCH                                                   |
|     +---------------------+    +---------------------+              |
|     | Vector Search (60%) |    | BM25 Search (40%)   |              |
|     | ChromaDB cosine     |    | Keyword matching    |              |
|     | similarity          |    |                     |              |
|     +---------+-----------+    +----------+----------+              |
|               |                           |                         |
|               +-----------+---------------+                         |
|                           |                                         |
|                           v                                         |
|                    Score Combination                                |
|     |                                                               |
|     v                                                               |
|  4. METADATA FILTERING                                              |
|     - property_type (warehouse/office)                              |
|     - location_region (Praha, Morava, etc.)                         |
|     - area_sqm range                                                |
|     - price_czk_sqm range                                           |
|     - availability                                                  |
|     |                                                               |
|     v                                                               |
|  5. LLM RERANKING                                                   |
|     Factors:                    Business Priority:                  |
|     - Type match (25%)          - is_hot bonus (+0.5)               |
|     - Location fit (25%)        - is_featured bonus (+0.5)          |
|     - Region match              - exact_match bonus (+1.0)          |
|     - Size adequacy (20%)                                           |
|     - Price fit (20%)                                               |
|     - Availability (10%)                                            |
|     |                                                               |
|     v                                                               |
|  6. TOP-K RESULTS                                                   |
|                                                                     |
+---------------------------------------------------------------------+
```

---

## Lead Scoring Model

```
+---------------------------------------------------------------------+
|                    LEAD SCORING (0-100)                             |
+---------------------------------------------------------------------+
|                                                                     |
|  COMPLETENESS (30 pts max)                                          |
|  - property_type specified       -> +6 pts                          |
|  - area range specified          -> +6 pts                          |
|  - locations/regions specified   -> +6 pts                          |
|  - budget specified              -> +6 pts                          |
|  - timeline specified            -> +6 pts                          |
|                                                                     |
|  REALISM (30 pts max)                                               |
|  Budget vs Market:           Area:              Urgency:            |
|  - >=90% avg -> +12         - <=500m2 -> +8    immediate -> +10    |
|  - >=70% avg -> +8          - <=1000m2 -> +6   1-3mo -> +10        |
|  - >=50% avg -> +4          - <=2000m2 -> +4   3-6mo -> +6         |
|  - <50% avg -> +0           - >2000m2 -> +2    flexible -> +4      |
|                                                                     |
|  MATCH QUALITY (25 pts max)                                         |
|  Criteria fit (0-20 pts):        Match count bonus:                 |
|  - type match      (5 pts)       - >=3 matches -> +5 pts            |
|  - area match      (5 pts)       - >=2 matches -> +3 pts            |
|  - price match     (5 pts)                                          |
|  - location match  (5 pts)                                          |
|                                                                     |
|  ENGAGEMENT (15 pts max)                                            |
|  - email provided            -> +6 pts                              |
|  - phone provided            -> +4 pts                              |
|  - company specified         -> +3 pts                              |
|  - name provided             -> +2 pts                              |
|                                                                     |
|  QUALITY TIERS                                                      |
|  - HOT  (70-100): Priority contact immediately                      |
|  - WARM (40-69):  Contact within 24 hours                           |
|  - COLD (0-39):   Nurture campaign                                  |
|                                                                     |
+---------------------------------------------------------------------+
```

---

## Technology Stack

| Layer | Technology |
|-------|------------|
| UI | Streamlit |
| LLM | OpenAI GPT-4o-mini |
| Embeddings | OpenAI text-embedding-3-small |
| Vector DB | ChromaDB |
| Relational DB | SQLite |
| Framework | LangChain |
| Validation | Pydantic |

---

## Key Design Decisions

1. **Hybrid Search**: Combining vector similarity (60%) with BM25 keyword matching (40%) ensures both semantic understanding and exact term matching.

2. **Query Expansion**: Czech language support with synonyms and location variants improves recall for local searches.

3. **Region Detection**: Automatic normalization of Czech regions (Praha, Morava, etc.) enables precise filtering by geographic area.

4. **Dual-Database Architecture**: SQLite for transactional data (leads, conversations), ChromaDB for vector search - optimal combination for different query types.

5. **LLM Reranking**: Final pass with GPT ensures business priorities (featured listings, exact matches) are properly weighted.

6. **Phase-Aware Conversations**: 7 distinct phases (greeting -> handoff) enable context-appropriate responses.

7. **Multi-Factor Scoring**: 4-component lead scoring provides transparent, explainable qualification.
