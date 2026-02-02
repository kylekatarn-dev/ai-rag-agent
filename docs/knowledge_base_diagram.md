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
| **Praha** | Prague 1-10, Prague surroundings | Pankrác, Karlín, Smíchov, Hostivice |
| **Střední Čechy** | Central Bohemia | Mladá Boleslav, Kladno, Kolín |
| **Jižní Čechy** | South Bohemia | České Budějovice, Tábor |
| **Západní Čechy** | West Bohemia (Plzeň, Karlovy Vary) | Plzeň, Karlovy Vary |
| **Severní Čechy** | North Bohemia (Ústí, Liberec) | Ústí nad Labem, Liberec |
| **Východní Čechy** | East Bohemia (Hradec, Pardubice) | Hradec Králové, Pardubice |
| **Jižní Morava** | South Moravia | Brno, Znojmo |
| **Severní Morava** | North Moravia (Olomouc, Ostrava) | Ostrava, Olomouc |

Region detection is performed automatically from query text using:
- Direct city/area name matching
- Synonyms and variants (e.g., "near Prague" → Praha)
- Postal codes (if provided)

---

## Entity Relationship Diagram

```
                                    ┌──────────────────────────────────────────┐
                                    │              VECTOR STORE                │
                                    │              (ChromaDB)                  │
                                    │                                          │
                                    │  ┌────────────────────────────────────┐  │
                                    │  │     Property Embeddings            │  │
                                    │  │     (text-embedding-3-small)       │  │
                                    │  │                                    │  │
                                    │  │  • Semantic text representation    │  │
                                    │  │  • Metadata filters                │  │
                                    │  │  • Priority scores                 │  │
                                    │  └────────────────────────────────────┘  │
                                    └──────────────────┬───────────────────────┘
                                                       │
                              ┌─────────────────────────────────────────────────┐
                              │                                                 │
                              ▼                                                 ▼
┌─────────────────────────────────────────┐         ┌─────────────────────────────────────────┐
│            PROPERTY (Nemovitost)        │         │              LEAD (Klient)              │
├─────────────────────────────────────────┤         ├─────────────────────────────────────────┤
│ Core Attributes:                        │         │ Identification:                         │
│  • id (int, PK)                         │         │  • id (UUID, PK)                        │
│  • property_type (warehouse|office)     │◄───────►│  • created_at (datetime)                │
│  • location (string)                    │   M:N   │                                         │
│  • location_region (string)             │  match  │ Contact Info:                           │
│  • area_sqm (int)                       │         │  • name, email, phone, company          │
│  • price_czk_sqm (int)                  │         │                                         │
│  • availability (string|date)           │         │ Requirements:                           │
│  • parking_spaces (int)                 │         │  • property_type (warehouse|office)     │
│  • amenities (list[string])             │         │  • min_area_sqm, max_area_sqm           │
│                                         │         │  • preferred_locations (list)           │
│ Business Attributes:                    │         │  • preferred_regions (list)             │
│  • is_featured (bool)                   │         │  • max_price_czk_sqm                    │
│  • is_hot (bool)                        │         │  • move_in_urgency                      │
│  • priority_score (0-100)               │         │                                         │
│  • commission_rate (float)              │         │ Qualification:                          │
│                                         │         │  • lead_score (0-100)                   │
│ Computed Fields:                        │         │  • lead_quality (HOT|WARM|COLD)         │
│  • total_monthly_rent                   │         │  • customer_type                        │
│  • is_available_now                     │         │  • matched_properties (list[int])       │
│  • value_score                          │         │                                         │
│  • location_region (normalized)         │         │ Status:                                 │
└─────────────────────────────────────────┘         │  • status (new→qualified→closed)        │
              │                                     │  • assigned_broker_id                   │
              │                                     │  • conversation_summary                 │
              │ 1:N                                 └─────────────────────────────────────────┘
              │ assigned                                           │
              ▼                                                    │ 1:N
┌─────────────────────────────────────────┐                        │ owns
│            BROKER (Makléř)              │                        ▼
├─────────────────────────────────────────┤         ┌─────────────────────────────────────────┐
│  • id (int, PK)                         │         │          CONVERSATION (Konverzace)      │
│  • name, email, phone                   │◄────────┤─────────────────────────────────────────┤
│  • specialization (warehouse|office)    │   1:N   │  • lead (Lead ref)                      │
│  • regions (list[string])               │  handles│  • messages (list[Message])             │
│  • is_available (bool)                  │         │  • current_phase (enum)                 │
│  • current_leads_count                  │         │  • properties_shown (list[int])         │
│  • max_leads (capacity)                 │         │  • questions_asked (list[str])          │
└─────────────────────────────────────────┘         │  • created_at, updated_at               │
                                                    └─────────────────────────────────────────┘
```

---

## Database Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              DATABASE LAYER                                         │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│   ┌───────────────────────────────────┐     ┌───────────────────────────────────┐   │
│   │           SQLite                  │     │          ChromaDB                 │   │
│   │    (Relational Database)          │     │    (Vector Database)              │   │
│   ├───────────────────────────────────┤     ├───────────────────────────────────┤   │
│   │                                   │     │                                   │   │
│   │  Tables:                          │     │  Collections:                     │   │
│   │  • leads                          │     │  • properties                     │   │
│   │  • conversations                  │     │                                   │   │
│   │  • brokers                        │     │  Stores:                          │   │
│   │  • messages                       │     │  • Vector embeddings              │   │
│   │                                   │     │  • Property metadata              │   │
│   │  Stores:                          │     │  • Document IDs                   │   │
│   │  • Client contact info            │     │                                   │   │
│   │  • Conversation history           │     │  Persistence:                     │   │
│   │  • Lead scores and status         │     │  • ./chroma_db                    │   │
│   │  • Broker assignments             │     │                                   │   │
│   │                                   │     │                                   │   │
│   │  File: ./data/app.db              │     │                                   │   │
│   └───────────────────────────────────┘     └───────────────────────────────────┘   │
│                                                                                     │
│   Implementation: app/persistence/database.py, app/persistence/repositories.py     │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## RAG Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                 RAG PIPELINE                                        │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│   ┌─────────────┐     ┌─────────────────┐     ┌─────────────────┐                   │
│   │ User Query  │────►│ Query Expansion │────►│ Multi-Query     │                   │
│   │ (Czech NL)  │     │ • Synonyms      │     │ Retrieval       │                   │
│   │             │     │ • Location vars │     │ • 3 query vars  │                   │
│   └─────────────┘     │ • Region detect │     └────────┬────────┘                   │
│                       └─────────────────┘              │                            │
│                                                        ▼                            │
│   ┌─────────────────────────────────────────────────────────────────────────────┐   │
│   │                        HYBRID SEARCH                                        │   │
│   │  ┌─────────────────────┐         ┌─────────────────────┐                    │   │
│   │  │  Vector Search (60%)│         │   BM25 Search (40%) │                    │   │
│   │  │  ChromaDB cosine    │         │   Keyword matching  │                    │   │
│   │  │  similarity         │         │                     │                    │   │
│   │  └──────────┬──────────┘         └──────────┬──────────┘                    │   │
│   │             └────────────────┬───────────────┘                              │   │
│   │                              ▼                                              │   │
│   │                     Score Combination                                       │   │
│   └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                        │                            │
│                                                        ▼                            │
│   ┌─────────────────────────────────────────────────────────────────────────────┐   │
│   │                      METADATA FILTERING                                     │   │
│   │  • property_type (warehouse/office)                                         │   │
│   │  • location_region (Praha, Morava, etc.)                                    │   │
│   │  • area_sqm range                                                           │   │
│   │  • price_czk_sqm range                                                      │   │
│   │  • availability                                                             │   │
│   └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                        │                            │
│                                                        ▼                            │
│   ┌─────────────────────────────────────────────────────────────────────────────┐   │
│   │                      LLM RERANKING                                          │   │
│   │  Factors:                          Business Priority:                       │   │
│   │  • Type match (25%)                • is_hot bonus (+0.5)                    │   │
│   │  • Location fit (25%)              • is_featured bonus (+0.5)               │   │
│   │  • Region match                    • exact_match bonus (+1.0)               │   │
│   │  • Size adequacy (20%)                                                      │   │
│   │  • Price fit (20%)                                                          │   │
│   │  • Availability (10%)                                                       │   │
│   └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                        │                            │
│                                                        ▼                            │
│                                                ┌───────────────┐                    │
│                                                │  Top K        │                    │
│                                                │  Properties   │                    │
│                                                └───────────────┘                    │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Lead Scoring Model

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                            LEAD SCORING (0-100)                                     │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│   ┌───────────────────────────────────────────────────────────────────────────┐     │
│   │  COMPLETENESS (30 pts max)                                                │     │
│   │  ├── property_type specified       → +6 pts                               │     │
│   │  ├── area range specified          → +6 pts                               │     │
│   │  ├── locations/regions specified   → +6 pts                               │     │
│   │  ├── budget specified              → +6 pts                               │     │
│   │  └── timeline specified            → +6 pts                               │     │
│   └───────────────────────────────────────────────────────────────────────────┘     │
│                                                                                     │
│   ┌───────────────────────────────────────────────────────────────────────────┐     │
│   │  REALISM (30 pts max)                                                     │     │
│   │  Budget vs Market:                 Area:                  Urgency:        │     │
│   │  ├── ≥90% avg → +12               ├── ≤500m² → +8        immediate → +10 │     │
│   │  ├── ≥70% avg → +8                ├── ≤1000m² → +6       1-3mo → +10     │     │
│   │  ├── ≥50% avg → +4                ├── ≤2000m² → +4       3-6mo → +6      │     │
│   │  └── <50% avg → +0                └── >2000m² → +2       flexible → +4   │     │
│   └───────────────────────────────────────────────────────────────────────────┘     │
│                                                                                     │
│   ┌───────────────────────────────────────────────────────────────────────────┐     │
│   │  MATCH QUALITY (25 pts max)                                               │     │
│   │  Criteria fit (0-20 pts):          Match count bonus:                     │     │
│   │  ├── type match      (5 pts)       ├── ≥3 matches → +5 pts                │     │
│   │  ├── area match      (5 pts)       └── ≥2 matches → +3 pts                │     │
│   │  ├── price match     (5 pts)                                              │     │
│   │  └── location match  (5 pts)                                              │     │
│   └───────────────────────────────────────────────────────────────────────────┘     │
│                                                                                     │
│   ┌───────────────────────────────────────────────────────────────────────────┐     │
│   │  ENGAGEMENT (15 pts max)                                                  │     │
│   │  ├── email provided            → +6 pts                                   │     │
│   │  ├── phone provided            → +4 pts                                   │     │
│   │  ├── company specified         → +3 pts                                   │     │
│   │  └── name provided             → +2 pts                                   │     │
│   └───────────────────────────────────────────────────────────────────────────┘     │
│                                                                                     │
│   ┌───────────────────────────────────────────────────────────────────────────┐     │
│   │  QUALITY TIERS                                                            │     │
│   │  ├── HOT  (70-100): Priority contact immediately                          │     │
│   │  ├── WARM (40-69):  Contact within 24 hours                               │     │
│   │  └── COLD (0-39):   Nurture campaign                                      │     │
│   └───────────────────────────────────────────────────────────────────────────┘     │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Detailed Summary

### 1. Entities Overview

| Entity | Purpose | Key Attributes | Record Count |
|--------|---------|----------------|--------------|
| **Property** | Commercial real estate listings | type, location, region, area, price, availability | 20 |
| **Lead** | Potential client with requirements | requirements, contact info, score, preferred regions | Dynamic |
| **Broker** | Real estate agent | specialization, regions, capacity | Configurable |
| **Conversation** | Chat session state | messages, phase, shown properties | Per session |

### 2. Property Entity Details

**Core Fields:**
- `property_type`: "warehouse" (sklad) or "office" (kancelář)
- `location`: Full address (e.g., "Praha 4 - Pankrác")
- `location_region`: Normalized region (Praha, Jižní Morava, etc.)
- `area_sqm`: Size in square meters (60-2000 m²)
- `price_czk_sqm`: Monthly rent per m² (75-450 Kč)
- `availability`: "ihned" (immediate) or date string

**Business Fields:**
- `is_featured`: Manually promoted listing
- `is_hot`: Special/urgent offer
- `priority_score`: 0-100 ranking for search results

**Computed Fields:**
- `total_monthly_rent`: area × price
- `is_available_now`: availability == "ihned"
- `value_score`: Price compared to market average
- `location_region`: Automatically derived region from address

### 3. Lead Entity Details

**Requirements Captured:**
- Property type (warehouse/office)
- Area range (min/max m²)
- Preferred locations (list)
- Preferred regions (list - Praha, Morava, etc.)
- Budget (max Kč/m²/month)
- Move-in urgency (immediate/1-3mo/3-6mo/flexible)

**Qualification Data:**
- `lead_score`: 0-100 calculated score
- `lead_quality`: HOT/WARM/COLD tier
- `customer_type`: INFORMED/VAGUE/UNREALISTIC
- `matched_properties`: List of matching property IDs

### 4. Database Configuration

#### SQLite (Relational Data)

| Setting | Value |
|---------|-------|
| Database | SQLite |
| File | `./data/app.db` |
| Implementation | `app/persistence/database.py` |
| Repository | `app/persistence/repositories.py` |

**Tables:**
- `leads` - Client data and requirements
- `conversations` - Conversation history
- `messages` - Individual messages
- `brokers` - Broker information

#### ChromaDB (Vector Data)

| Setting | Value |
|---------|-------|
| Database | ChromaDB (persistent) |
| Embedding Model | OpenAI text-embedding-3-small |
| Similarity Metric | Cosine similarity |
| Persistence Path | `./chroma_db` |

**Indexed Metadata:**
- `property_type` (string filter)
- `location_region` (string filter - Czech region)
- `area_sqm` (numeric range)
- `price_czk_sqm` (numeric range)
- `is_available_now` (boolean filter)
- `priority_score` (numeric sort)

### 5. Search Pipeline Components

| Component | File | Purpose |
|-----------|------|---------|
| Embeddings | `app/rag/embeddings.py` | Generate vector representations |
| Vector Store | `app/rag/vectorstore.py` | ChromaDB CRUD operations |
| Hybrid Search | `app/rag/hybrid_search.py` | Combine vector + BM25 |
| Query Expansion | `app/rag/query_expansion.py` | Czech synonyms, location variants, region detection |
| Reranker | `app/rag/reranker.py` | LLM-based relevance scoring |
| Retriever | `app/rag/retriever.py` | High-level search interface |
| Regions | `app/utils/regions.py` | Czech region normalization and detection |

### 6. Scoring Formula Summary

```
Total Score = Completeness (30%) + Realism (30%) + Match Quality (25%) + Engagement (15%)

Where:
- Completeness = Sum of (type + area + location/region + budget + timeline) × 6 pts each
- Realism = Budget fit (0-12) + Area size (2-8) + Urgency (4-10)
- Match Quality = Criteria fit (0-20) + Match count bonus (0-5)
- Engagement = Contact info provided (email=6, phone=4, company=3, name=2)
```

### 7. Data Flow

```
User Input → Query Expansion → Region Detection → Multi-Query Search →
Hybrid Scoring → Metadata Filter (including region) → LLM Rerank →
Top-K Results → Display to User

Data Storage:
- Properties → ChromaDB (vectors + metadata)
- Leads, Conversations → SQLite (relational data)
```

### 8. Technology Stack

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

6. **Phase-Aware Conversations**: 7 distinct phases (greeting → handoff) enable context-appropriate responses.

7. **Multi-Factor Scoring**: 4-component lead scoring provides transparent, explainable qualification.
