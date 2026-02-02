# AI Asistent pro Realitní Kancelář

Inteligentní konverzační asistent pro komerční nemovitosti využívající RAG (Retrieval-Augmented Generation) a pokročilé hodnocení leadů.

## Obsah

- [Spuštění](#spuštění)
- [Datový model](#datový-model)
- [RAG Pipeline](#rag-pipeline)
- [Lead Scoring](#lead-scoring)
- [Testovací scénáře](#testovací-scénáře)
- [Architektura](#architektura)

---

## Spuštění

### Požadavky

- Python 3.11+
- OpenAI API klíč

### Instalace

```bash
# 1. Klonování repozitáře
git clone https://github.com/kylekatarn-dev/ai-rag-agent.git

# 2. Vytvoření virtuálního prostředí
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate

# 3. Instalace závislostí
pip install -r requirements.txt

# 4. Konfigurace
cp .env.example .env
# Upravte .env a doplňte OPENAI_API_KEY
```

### Konfigurace (.env)

```env
# Povinné
OPENAI_API_KEY=sk-your-api-key-here

# Volitelné (výchozí hodnoty)
OPENAI_MODEL=gpt-4o-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
CHROMA_PERSIST_DIR=./chroma_db

# RAG nastavení
RAG_USE_HYBRID_SEARCH=true
RAG_USE_QUERY_EXPANSION=true
RAG_USE_RERANKING=true
```

### Spuštění aplikace

```bash
# Inicializace databáze (první spuštění)
python scripts/init_database.py

# Spuštění Streamlit aplikace
streamlit run app/main.py
```

Aplikace bude dostupná na `http://localhost:8501`


## Datový model

Systém využívá **4 hlavní entity** uložené v SQLite (relační data) a ChromaDB (vektorová data).

### Entity

#### 1. Property (Nemovitost)

| Atribut | Typ | Popis |
|---------|-----|-------|
| `id` | int | Primární klíč |
| `property_type` | enum | "warehouse" (sklad) / "office" (kancelář) |
| `location` | string | Adresa (např. "Praha 4 - Pankrác") |
| `location_region` | string | Normalizovaný region (Praha, Morava, atd.) |
| `area_sqm` | int | Plocha v m² |
| `price_czk_sqm` | int | Cena za m²/měsíc v Kč |
| `availability` | string | "ihned" nebo datum |
| `parking_spaces` | int | Počet parkovacích míst |
| `amenities` | list | Vybavení (rampa, klimatizace, atd.) |
| `is_featured` | bool | Propagovaná nabídka |
| `is_hot` | bool | Urgentní/lukrativní nabídka |
| `priority_score` | int | Skóre priority 0-100 |

**Vypočítaná pole:**
- `total_monthly_rent` = area × price
- `is_available_now` = availability == "ihned"
- `value_score` = porovnání s tržním průměrem

#### 2. Lead (Potenciální klient)

| Atribut | Typ | Popis |
|---------|-----|-------|
| `id` | UUID | Unikátní identifikátor |
| `name` | string | Jméno klienta |
| `email` | string | E-mail |
| `phone` | string | Telefon |
| `company` | string | Firma |
| `property_type` | enum | Požadovaný typ nemovitosti |
| `min_area_sqm` | int | Minimální plocha |
| `max_area_sqm` | int | Maximální plocha |
| `preferred_locations` | list | Preferované lokality |
| `max_price_czk_sqm` | int | Maximální rozpočet |
| `move_in_urgency` | enum | Naléhavost (immediate/1-3months/...) |
| `lead_score` | int | Skóre 0-100 |
| `lead_quality` | enum | HOT/WARM/COLD |
| `customer_type` | enum | INFORMED/VAGUE/UNREALISTIC |
| `matched_properties` | list | ID odpovídajících nemovitostí |

#### 3. Broker (Makléř)

| Atribut | Typ | Popis |
|---------|-----|-------|
| `id` | int | Primární klíč |
| `name` | string | Jméno |
| `email` | string | E-mail |
| `phone` | string | Telefon |
| `specialization` | enum | Specializace (sklad/kancelář) |
| `regions` | list | Obsluhované regiony |
| `is_available` | bool | Dostupnost |
| `max_leads` | int | Maximální kapacita leadů |

#### 4. Conversation (Konverzace)

| Atribut | Typ | Popis |
|---------|-----|-------|
| `lead` | Lead | Reference na leada |
| `messages` | list | Historie zpráv |
| `current_phase` | enum | Aktuální fáze konverzace |
| `properties_shown` | list | Zobrazené nemovitosti |
| `questions_asked` | list | Položené otázky |

### Databázová architektura

```
┌─────────────────────────┐     ┌─────────────────────────┐
│        SQLite           │     │       ChromaDB          │
│   (Relační data)        │     │   (Vektorová data)      │
├─────────────────────────┤     ├─────────────────────────┤
│ • leads                 │     │ • property embeddings   │
│ • conversations         │     │ • metadata filtry       │
│ • brokers               │     │ • similarity search     │
│ • messages              │     │                         │
│                         │     │ Soubor: ./chroma_db     │
│ Soubor: ./data/app.db   │     │                         │
└─────────────────────────┘     └─────────────────────────┘
```

---

## RAG Pipeline

Systém využívá **hybridní RAG pipeline** pro vyhledávání nemovitostí.

### Architektura

```
┌─────────────────────────────────────────────────────────────────────┐
│                         RAG PIPELINE                                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  1. DOTAZ UŽIVATELE (čeština)                                       │
│     │                                                               │
│     ▼                                                               │
│  2. ROZŠÍŘENÍ DOTAZU (Query Expansion)                              │
│     • České synonyma (sklad → warehouse, skladiště, hala)           │
│     • Varianty lokalit (Praha → Praha 1-10, okolí Prahy)            │
│     • Detekce regionu (Brno → Jižní Morava)                         │
│     │                                                               │
│     ▼                                                               │
│  3. HYBRIDNÍ VYHLEDÁVÁNÍ                                            │
│     ┌─────────────────────┐  ┌─────────────────────┐                │
│     │ Vektorové (60%)     │  │ BM25 (40%)          │                │
│     │ • ChromaDB          │  │ • Klíčová slova     │                │
│     │ • Cosine similarity │  │ • Přesné shody      │                │
│     └─────────┬───────────┘  └──────────┬──────────┘                │
│               └──────────┬──────────────┘                           │
│                          ▼                                          │
│  4. FILTROVÁNÍ METADAT                                              │
│     • property_type (sklad/kancelář)                                │
│     • location_region (Praha, Morava, atd.)                         │
│     • area_sqm (rozsah plochy)                                      │
│     • price_czk_sqm (cenový rozsah)                                 │
│     • availability (dostupnost)                                     │
│     │                                                               │
│     ▼                                                               │
│  5. LLM RERANKING                                                   │
│     • Shoda typu (25%)                                              │
│     • Shoda lokality (25%)                                          │
│     • Vhodnost velikosti (20%)                                      │
│     • Shoda ceny (20%)                                              │
│     • Dostupnost (10%)                                              │
│     • Bonusy: is_hot (+0.5), is_featured (+0.5), exact_match (+1.0) │
│     │                                                               │
│     ▼                                                               │
│  6. TOP-K VÝSLEDKY                                                  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Komponenty

| Komponenta | Soubor | Popis |
|------------|--------|-------|
| Embeddings | `app/rag/embeddings.py` | OpenAI text-embedding-3-small |
| Vector Store | `app/rag/vectorstore.py` | ChromaDB integrace |
| Hybrid Search | `app/rag/hybrid_search.py` | Kombinace vector + BM25 |
| Query Expansion | `app/rag/query_expansion.py` | Rozšíření dotazů pro češtinu |
| Reranker | `app/rag/reranker.py` | LLM-based přeřazení |
| Retriever | `app/rag/retriever.py` | High-level rozhraní |

### Konfigurace RAG

V `.env` můžete zapnout/vypnout jednotlivé funkce:

```env
RAG_USE_HYBRID_SEARCH=true    # Hybridní vyhledávání (vector + BM25)
RAG_USE_QUERY_EXPANSION=true  # Rozšíření dotazů
RAG_USE_RERANKING=true        # LLM přeřazení výsledků
```

---

## Lead Scoring

Systém používá **scoring model 0-100** se čtyřmi váženými komponentami.

### Scoring Model

```
┌─────────────────────────────────────────────────────────────────────┐
│                    LEAD SCORING (0-100 bodů)                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ÚPLNOST INFORMACÍ (max 30 bodů)                                    │
│  ├── typ nemovitosti uveden        → +6 bodů                        │
│  ├── rozsah plochy uveden          → +6 bodů                        │
│  ├── lokality uvedeny              → +6 bodů                        │
│  ├── rozpočet uveden               → +6 bodů                        │
│  └── časový horizont uveden        → +6 bodů                        │
│                                                                     │
│  REALISTIČNOST POŽADAVKŮ (max 30 bodů)                              │
│  Rozpočet vs tržní průměr:         Plocha:          Naléhavost:     │
│  ├── ≥90% průměru → +12           ├── ≤500m² → +8  ihned → +10     │
│  ├── ≥70% průměru → +8            ├── ≤1000m² → +6 1-3 měs → +10   │
│  ├── ≥50% průměru → +4            ├── ≤2000m² → +4 3-6 měs → +6    │
│  └── <50% průměru → +0            └── >2000m² → +2 flexibilní → +4 │
│                                                                     │
│  SHODA S NABÍDKOU (max 25 bodů)                                     │
│  Shoda kritérií (0-20 bodů):       Bonus za počet shod:             │
│  ├── shoda typu       (5 bodů)     ├── ≥3 shody → +5 bodů           │
│  ├── shoda plochy     (5 bodů)     └── ≥2 shody → +3 body           │
│  ├── shoda ceny       (5 bodů)                                      │
│  └── shoda lokality   (5 bodů)                                      │
│                                                                     │
│  ENGAGEMENT (max 15 bodů)                                           │
│  ├── email uveden              → +6 bodů                            │
│  ├── telefon uveden            → +4 body                            │
│  ├── firma uvedena             → +3 body                            │
│  └── jméno uvedeno             → +2 body                            │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Kvalitativní úrovně

| Skóre | Úroveň | Akce |
|-------|--------|------|
| 70-100 | **HOT** | Prioritní kontakt ihned |
| 40-69 | **WARM** | Kontaktovat do 24 hodin |
| 0-39 | **COLD** | Nurture kampaň |

### Typy zákazníků

| Typ | Popis | Přístup |
|-----|-------|---------|
| **INFORMED** | Jasné požadavky, realistické | Přímé doporučení |
| **VAGUE** | Nejasné požadavky | Kvalifikační otázky |
| **UNREALISTIC** | Požadavky mimo trh | Vysvětlení reality, alternativy |

### Implementace

Scoring je implementován v `app/scoring/lead_scorer.py`:

```python
from app.scoring.lead_scorer import calculate_lead_score

score, quality, breakdown = calculate_lead_score(lead, matched_properties)
# score: 78
# quality: LeadQuality.HOT
# breakdown: {"completeness": 28, "realism": 26, "match_quality": 20, "engagement": 4}
```

---

## Testovací scénáře

### Scénář 1: Realistický a kvalitní lead

**Vstup:**
```
Klient: Dobrý den, hledám sklad v okolí Prahy, potřebuji asi 600-800 m²,
        s nákladovou rampou. Rozpočet mám do 110 Kč/m².
        Potřebuji to ideálně do měsíce.
```

**Očekávané chování:**
- Asistent identifikuje všechny klíčové parametry
- Vyhledá 2-3 odpovídající sklady v regionu Praha
- Lead score: 70+ (HOT)
- Customer type: INFORMED
- Vygeneruje souhrn pro makléře

### Scénář 2: Vágní dotaz

**Vstup:**
```
Klient: Potřeboval bych nějaký prostor pro firmu.
```

**Očekávané chování:**
- Asistent položí upřesňující otázky:
  - Jaký typ prostoru? (sklad/kancelář)
  - Jakou plochu potřebujete?
  - V jaké lokalitě?
  - Jaký je váš rozpočet?
- Lead score: 20-40 (COLD/WARM)
- Customer type: VAGUE

### Scénář 3: Nerealistické požadavky

**Vstup:**
```
Klient: Hledám kancelář v centru Prahy, 500 m²,
        maximálně za 50 Kč/m² měsíčně.
```

**Očekávané chování:**
- Asistent rozpozná nerealistický rozpočet (tržní průměr ~300+ Kč/m²)
- Vysvětlí tržní realitu
- Nabídne alternativy:
  - Menší plocha za stejnou cenu
  - Lokalita mimo centrum
  - Sdílené prostory
- Lead score: 30-50 (COLD/WARM)
- Customer type: UNREALISTIC

---

## Architektura

### Adresářová struktura

```
ai-rag-agent/
├── app/
│   ├── main.py              # Streamlit vstupní bod
│   ├── config.py            # Konfigurace
│   ├── agent/               # Konverzační AI
│   │   ├── chain.py         # RealEstateAgent
│   │   ├── prompts.py       # Systémové prompty
│   │   └── tools.py         # LangChain nástroje
│   ├── models/              # Pydantic modely
│   │   ├── property.py      # Nemovitost
│   │   ├── lead.py          # Lead
│   │   ├── broker.py        # Makléř
│   │   └── conversation.py  # Konverzace
│   ├── rag/                 # RAG pipeline
│   │   ├── vectorstore.py   # ChromaDB
│   │   ├── embeddings.py    # OpenAI embeddings
│   │   ├── retriever.py     # Vyhledávání
│   │   ├── hybrid_search.py # Hybridní search
│   │   ├── query_expansion.py # Rozšíření dotazů
│   │   └── reranker.py      # LLM reranking
│   ├── scoring/             # Lead scoring
│   │   └── lead_scorer.py   # Scoring algoritmus
│   ├── persistence/         # Databáze
│   │   ├── database.py      # SQLite
│   │   └── repositories.py  # Data access
│   ├── output/              # Výstupy
│   │   └── broker_summary.py # Souhrny pro makléře
│   └── utils/               # Utility
│       ├── regions.py       # Detekce regionů
│       └── validation.py    # Validace
├── data/                    # Data soubory
├── docs/                    # Dokumentace
├── tests/                   # Testy
├── scripts/                 # Skripty
│   └── init_database.py     # Inicializace DB
├── requirements.txt
├── Dockerfile
├── .env.example
└── README.md
```

### Technologie

| Komponenta | Technologie |
|------------|-------------|
| UI | Streamlit |
| LLM | OpenAI GPT-4o-mini |
| Embeddings | OpenAI text-embedding-3-small |
| Vektorová DB | ChromaDB |
| Relační DB | SQLite |
| Framework | LangChain |
| Validace | Pydantic |

---

## Licence

MIT License

---

## Kontakt

Pro dotazy a zpětnou vazbu vytvořte issue v repozitáři.
