# Architektura Knowledge Base

## Shrnutí

Tento dokument popisuje architekturu knowledge base pro AI asistenta realitní kanceláře. Systém využívá **hybridní RAG (Retrieval-Augmented Generation)** přístup kombinující:

- **Vektorové embeddings** pro sémantické vyhledávání podobnosti
- **BM25 keyword matching** pro přesné vyhledávání klíčových slov
- **LLM reranking** pro business-aware řazení výsledků
- **Strukturované filtrování metadat** pro přesné párování nemovitostí

Knowledge base obsahuje **4 hlavní entity**: Property (Nemovitost), Lead (Klient), Broker (Makléř) a Conversation (Konverzace), s relacemi umožňujícími kompletní správu životního cyklu leadu od prvního dotazu po předání makléři.

**Databázová vrstva**: Systém využívá **SQLite** pro perzistentní ukládání dat (leads, konverzace, makléři) a **ChromaDB** jako vektorovou databázi pro sémantické vyhledávání nemovitostí.

---

## Podporované regiony

Systém podporuje následující regiony České republiky:

| Region | Oblasti | Příklady lokalit |
|--------|---------|------------------|
| **Praha** | Praha 1-10, okolí Prahy | Pankrác, Karlín, Smíchov, Hostivice |
| **Střední Čechy** | Středočeský kraj | Mladá Boleslav, Kladno, Kolín |
| **Jižní Čechy** | Jihočeský kraj | České Budějovice, Tábor |
| **Západní Čechy** | Plzeňský, Karlovarský kraj | Plzeň, Karlovy Vary |
| **Severní Čechy** | Ústecký, Liberecký kraj | Ústí nad Labem, Liberec |
| **Východní Čechy** | Královéhradecký, Pardubický kraj | Hradec Králové, Pardubice |
| **Jižní Morava** | Jihomoravský kraj | Brno, Znojmo |
| **Severní Morava** | Olomoucký, Moravskoslezský kraj | Ostrava, Olomouc |

Detekce regionu probíhá automaticky z textu dotazu pomocí:
- Přímého názvu města/oblasti
- Synonym a variant (např. "u Prahy" → Praha)
- PSČ (pokud je uvedeno)

---

## Diagram entit a vztahů

```
                                    ┌──────────────────────────────────────────┐
                                    │           VEKTOROVÉ ÚLOŽIŠTĚ             │
                                    │              (ChromaDB)                  │
                                    │                                          │
                                    │  ┌────────────────────────────────────┐  │
                                    │  │     Embeddings nemovitostí         │  │
                                    │  │     (text-embedding-3-small)       │  │
                                    │  │                                    │  │
                                    │  │  • Sémantická reprezentace textu   │  │
                                    │  │  • Filtry metadat                  │  │
                                    │  │  • Skóre priority                  │  │
                                    │  └────────────────────────────────────┘  │
                                    └──────────────────┬───────────────────────┘
                                                       │
                              ┌─────────────────────────────────────────────────┐
                              │                                                 │
                              ▼                                                 ▼
┌─────────────────────────────────────────┐         ┌─────────────────────────────────────────┐
│            NEMOVITOST (Property)        │         │              KLIENT (Lead)              │
├─────────────────────────────────────────┤         ├─────────────────────────────────────────┤
│ Základní atributy:                      │         │ Identifikace:                           │
│  • id (int, PK)                         │         │  • id (UUID, PK)                        │
│  • property_type (sklad|kancelář)       │◄───────►│  • created_at (datetime)                │
│  • location (string)                    │   M:N   │                                         │
│  • location_region (string)             │  shoda  │ Kontaktní údaje:                        │
│  • area_sqm (int)                       │         │  • name, email, phone, company          │
│  • price_czk_sqm (int)                  │         │                                         │
│  • availability (string|datum)          │         │ Požadavky:                              │
│  • parking_spaces (int)                 │         │  • property_type (sklad|kancelář)       │
│  • amenities (list[string])             │         │  • min_area_sqm, max_area_sqm           │
│                                         │         │  • preferred_locations (list)           │
│ Business atributy:                      │         │  • preferred_regions (list)             │
│  • is_featured (bool)                   │         │  • max_price_czk_sqm                    │
│  • is_hot (bool)                        │         │  • move_in_urgency                      │
│  • priority_score (0-100)               │         │                                         │
│  • commission_rate (float)              │         │ Kvalifikace:                            │
│                                         │         │  • lead_score (0-100)                   │
│ Vypočítaná pole:                        │         │  • lead_quality (HOT|WARM|COLD)         │
│  • total_monthly_rent                   │         │  • customer_type                        │
│  • is_available_now                     │         │  • matched_properties (list[int])       │
│  • value_score                          │         │                                         │
│  • location_region (normalizovaný)      │         │ Status:                                 │
└─────────────────────────────────────────┘         │  • status (new→qualified→closed)        │
              │                                     │  • assigned_broker_id                   │
              │                                     │  • conversation_summary                 │
              │ 1:N                                 └─────────────────────────────────────────┘
              │ přiřazeno                                          │
              ▼                                                    │ 1:N
┌─────────────────────────────────────────┐                        │ vlastní
│            MAKLÉŘ (Broker)              │                        ▼
├─────────────────────────────────────────┤         ┌─────────────────────────────────────────┐
│  • id (int, PK)                         │         │          KONVERZACE (Conversation)      │
│  • name, email, phone                   │◄────────┤─────────────────────────────────────────┤
│  • specialization (sklad|kancelář)      │   1:N   │  • lead (Lead ref)                      │
│  • regions (list[string])               │ spravuje│  • messages (list[Message])             │
│  • is_available (bool)                  │         │  • current_phase (enum)                 │
│  • current_leads_count                  │         │  • properties_shown (list[int])         │
│  • max_leads (kapacita)                 │         │  • questions_asked (list[str])          │
└─────────────────────────────────────────┘         │  • created_at, updated_at               │
                                                    └─────────────────────────────────────────┘
```

---

## Databázová architektura

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              DATABÁZOVÁ VRSTVA                                      │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│   ┌───────────────────────────────────┐     ┌───────────────────────────────────┐   │
│   │           SQLite                  │     │          ChromaDB                 │   │
│   │    (Relační databáze)             │     │    (Vektorová databáze)           │   │
│   ├───────────────────────────────────┤     ├───────────────────────────────────┤   │
│   │                                   │     │                                   │   │
│   │  Tabulky:                         │     │  Kolekce:                         │   │
│   │  • leads                          │     │  • properties                     │   │
│   │  • conversations                  │     │                                   │   │
│   │  • brokers                        │     │  Ukládá:                          │   │
│   │  • messages                       │     │  • Vektorové embeddings           │   │
│   │                                   │     │  • Metadata nemovitostí           │   │
│   │  Ukládá:                          │     │  • ID dokumentů                   │   │
│   │  • Kontaktní údaje klientů        │     │                                   │   │
│   │  • Historie konverzací            │     │  Persistence:                     │   │
│   │  • Lead skóre a status            │     │  • ./chroma_db                    │   │
│   │  • Přiřazení makléřů              │     │                                   │   │
│   │                                   │     │                                   │   │
│   │  Soubor: ./data/app.db            │     │                                   │   │
│   └───────────────────────────────────┘     └───────────────────────────────────┘   │
│                                                                                     │
│   Implementace: app/persistence/database.py, app/persistence/repositories.py       │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Architektura RAG Pipeline

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                 RAG PIPELINE                                        │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│   ┌─────────────┐     ┌─────────────────┐     ┌─────────────────┐                   │
│   │ Dotaz       │────►│ Rozšíření       │────►│ Multi-Query     │                   │
│   │ uživatele   │     │ dotazu          │     │ vyhledávání     │                   │
│   │ (čeština)   │     │ • Synonyma      │     │ • 3 varianty    │                   │
│   └─────────────┘     │ • Lokality      │     └────────┬────────┘                   │
│                       │ • Detekce       │              │                            │
│                       │   regionu       │              │                            │
│                       └─────────────────┘              │                            │
│                                                        ▼                            │
│   ┌─────────────────────────────────────────────────────────────────────────────┐   │
│   │                      HYBRIDNÍ VYHLEDÁVÁNÍ                                   │   │
│   │  ┌─────────────────────┐         ┌─────────────────────┐                    │   │
│   │  │ Vektorové (60%)     │         │   BM25 (40%)        │                    │   │
│   │  │ ChromaDB cosine     │         │   Klíčová slova     │                    │   │
│   │  │ podobnost           │         │                     │                    │   │
│   │  └──────────┬──────────┘         └──────────┬──────────┘                    │   │
│   │             └────────────────┬───────────────┘                              │   │
│   │                              ▼                                              │   │
│   │                     Kombinace skóre                                         │   │
│   └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                        │                            │
│                                                        ▼                            │
│   ┌─────────────────────────────────────────────────────────────────────────────┐   │
│   │                      FILTROVÁNÍ METADAT                                     │   │
│   │  • property_type (sklad/kancelář)                                           │   │
│   │  • location_region (Praha, Morava, atd.)                                    │   │
│   │  • area_sqm rozsah                                                          │   │
│   │  • price_czk_sqm rozsah                                                     │   │
│   │  • dostupnost                                                               │   │
│   └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                        │                            │
│                                                        ▼                            │
│   ┌─────────────────────────────────────────────────────────────────────────────┐   │
│   │                      LLM PŘEŘAZENÍ                                          │   │
│   │  Faktory:                          Business priorita:                       │   │
│   │  • Shoda typu (25%)                • is_hot bonus (+0.5)                    │   │
│   │  • Shoda lokality (25%)            • is_featured bonus (+0.5)               │   │
│   │  • Shoda regionu                   • exact_match bonus (+1.0)               │   │
│   │  • Vhodnost velikosti (20%)                                                 │   │
│   │  • Shoda ceny (20%)                                                         │   │
│   │  • Dostupnost (10%)                                                         │   │
│   └─────────────────────────────────────────────────────────────────────────────┘   │
│                                                        │                            │
│                                                        ▼                            │
│                                                ┌───────────────┐                    │
│                                                │  Top K        │                    │
│                                                │  nemovitostí  │                    │
│                                                └───────────────┘                    │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Model hodnocení leadů

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                         LEAD SCORING (0-100 bodů)                                   │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│   ┌───────────────────────────────────────────────────────────────────────────┐     │
│   │  ÚPLNOST (max 30 bodů)                                                    │     │
│   │  ├── typ nemovitosti uveden        → +6 bodů                              │     │
│   │  ├── rozsah plochy uveden          → +6 bodů                              │     │
│   │  ├── lokality/regiony uvedeny      → +6 bodů                              │     │
│   │  ├── rozpočet uveden               → +6 bodů                              │     │
│   │  └── časový horizont uveden        → +6 bodů                              │     │
│   └───────────────────────────────────────────────────────────────────────────┘     │
│                                                                                     │
│   ┌───────────────────────────────────────────────────────────────────────────┐     │
│   │  REALISTIČNOST (max 30 bodů)                                              │     │
│   │  Rozpočet vs trh:                  Plocha:               Naléhavost:      │     │
│   │  ├── ≥90% prům → +12              ├── ≤500m² → +8       ihned → +10      │     │
│   │  ├── ≥70% prům → +8               ├── ≤1000m² → +6      1-3 měs → +10    │     │
│   │  ├── ≥50% prům → +4               ├── ≤2000m² → +4      3-6 měs → +6     │     │
│   │  └── <50% prům → +0               └── >2000m² → +2      flexibilní → +4  │     │
│   └───────────────────────────────────────────────────────────────────────────┘     │
│                                                                                     │
│   ┌───────────────────────────────────────────────────────────────────────────┐     │
│   │  KVALITA SHODY (max 25 bodů)                                              │     │
│   │  Shoda kritérií (0-20 bodů):       Bonus za počet shod:                   │     │
│   │  ├── shoda typu       (5 bodů)     ├── ≥3 shody → +5 bodů                 │     │
│   │  ├── shoda plochy     (5 bodů)     └── ≥2 shody → +3 bodů                 │     │
│   │  ├── shoda ceny       (5 bodů)                                            │     │
│   │  └── shoda lokality   (5 bodů)                                            │     │
│   └───────────────────────────────────────────────────────────────────────────┘     │
│                                                                                     │
│   ┌───────────────────────────────────────────────────────────────────────────┐     │
│   │  ENGAGEMENT (max 15 bodů)                                                 │     │
│   │  ├── email uveden              → +6 bodů                                  │     │
│   │  ├── telefon uveden            → +4 body                                  │     │
│   │  ├── firma uvedena             → +3 body                                  │     │
│   │  └── jméno uvedeno             → +2 body                                  │     │
│   └───────────────────────────────────────────────────────────────────────────┘     │
│                                                                                     │
│   ┌───────────────────────────────────────────────────────────────────────────┐     │
│   │  KVALITATIVNÍ ÚROVNĚ                                                      │     │
│   │  ├── HOT  (70-100): Prioritní kontakt ihned                               │     │
│   │  ├── WARM (40-69):  Kontaktovat do 24 hodin                               │     │
│   │  └── COLD (0-39):   Nurture kampaň                                        │     │
│   └───────────────────────────────────────────────────────────────────────────┘     │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Podrobné shrnutí

### 1. Přehled entit

| Entita | Účel | Klíčové atributy | Počet záznamů |
|--------|------|------------------|---------------|
| **Nemovitost** | Nabídky komerčních nemovitostí | typ, lokalita, region, plocha, cena, dostupnost | 20 |
| **Lead** | Potenciální klient s požadavky | požadavky, kontakt, skóre, preferované regiony | Dynamický |
| **Makléř** | Realitní makléř | specializace, regiony, kapacita | Konfigurovatelné |
| **Konverzace** | Stav chatové relace | zprávy, fáze, zobrazené nemovitosti | Dle relace |

### 2. Detaily entity Nemovitost

**Základní pole:**
- `property_type`: "warehouse" (sklad) nebo "office" (kancelář)
- `location`: Plná adresa (např. "Praha 4 - Pankrác")
- `location_region`: Normalizovaný region (Praha, Jižní Morava, atd.)
- `area_sqm`: Velikost v metrech čtverečních (60-2000 m²)
- `price_czk_sqm`: Měsíční nájem za m² (75-450 Kč)
- `availability`: "ihned" nebo řetězec s datem

**Business pole:**
- `is_featured`: Ručně propagovaná nabídka
- `is_hot`: Speciální/urgentní nabídka
- `priority_score`: Hodnocení 0-100 pro řazení výsledků

**Vypočítaná pole:**
- `total_monthly_rent`: plocha × cena
- `is_available_now`: availability == "ihned"
- `value_score`: Cena v porovnání s tržním průměrem
- `location_region`: Automaticky odvozený region z adresy

### 3. Detaily entity Lead

**Zachycené požadavky:**
- Typ nemovitosti (sklad/kancelář)
- Rozsah plochy (min/max m²)
- Preferované lokality (seznam)
- Preferované regiony (seznam - Praha, Morava, atd.)
- Rozpočet (max Kč/m²/měsíc)
- Naléhavost nastěhování (ihned/1-3měs/3-6měs/flexibilní)

**Kvalifikační data:**
- `lead_score`: Vypočítané skóre 0-100
- `lead_quality`: Úroveň HOT/WARM/COLD
- `customer_type`: INFORMED/VAGUE/UNREALISTIC
- `matched_properties`: Seznam ID odpovídajících nemovitostí

### 4. Konfigurace databází

#### SQLite (Relační data)

| Nastavení | Hodnota |
|-----------|---------|
| Databáze | SQLite |
| Soubor | `./data/app.db` |
| Implementace | `app/persistence/database.py` |
| Repository | `app/persistence/repositories.py` |

**Tabulky:**
- `leads` - Údaje o klientech a jejich požadavky
- `conversations` - Historie konverzací
- `messages` - Jednotlivé zprávy
- `brokers` - Informace o makléřích

#### ChromaDB (Vektorová data)

| Nastavení | Hodnota |
|-----------|---------|
| Databáze | ChromaDB (perzistentní) |
| Model embeddings | OpenAI text-embedding-3-small |
| Metrika podobnosti | Kosinová podobnost |
| Cesta perzistence | `./chroma_db` |

**Indexovaná metadata:**
- `property_type` (filtr string)
- `location_region` (filtr string - region ČR)
- `area_sqm` (numerický rozsah)
- `price_czk_sqm` (numerický rozsah)
- `is_available_now` (boolean filtr)
- `priority_score` (numerické řazení)

### 5. Komponenty vyhledávacího pipeline

| Komponenta | Soubor | Účel |
|------------|--------|------|
| Embeddings | `app/rag/embeddings.py` | Generování vektorových reprezentací |
| Vektorové úložiště | `app/rag/vectorstore.py` | ChromaDB CRUD operace |
| Hybridní vyhledávání | `app/rag/hybrid_search.py` | Kombinace vektor + BM25 |
| Rozšíření dotazu | `app/rag/query_expansion.py` | České synonyma, varianty lokalit, detekce regionů |
| Přeřazení | `app/rag/reranker.py` | LLM-based hodnocení relevance |
| Retriever | `app/rag/retriever.py` | High-level vyhledávací rozhraní |
| Regiony | `app/utils/regions.py` | Normalizace a detekce regionů ČR |

### 6. Shrnutí vzorce scoringu

```
Celkové skóre = Úplnost (30%) + Realističnost (30%) + Kvalita shody (25%) + Engagement (15%)

Kde:
- Úplnost = Součet (typ + plocha + lokalita/region + rozpočet + časový horizont) × 6 bodů
- Realističnost = Shoda rozpočtu (0-12) + Velikost plochy (2-8) + Naléhavost (4-10)
- Kvalita shody = Shoda kritérií (0-20) + Bonus za počet shod (0-5)
- Engagement = Poskytnuté kontaktní údaje (email=6, telefon=4, firma=3, jméno=2)
```

### 7. Tok dat

```
Vstup uživatele → Rozšíření dotazu → Detekce regionu → Multi-Query vyhledávání →
Hybridní scoring → Filtr metadat (včetně regionu) → LLM přeřazení →
Top-K výsledky → Zobrazení uživateli

Ukládání dat:
- Nemovitosti → ChromaDB (vektory + metadata)
- Leads, Konverzace → SQLite (relační data)
```

### 8. Technologický stack

| Vrstva | Technologie |
|--------|-------------|
| UI | Streamlit |
| LLM | OpenAI GPT-4o-mini |
| Embeddings | OpenAI text-embedding-3-small |
| Vektorová DB | ChromaDB |
| Relační DB | SQLite |
| Framework | LangChain |
| Validace | Pydantic |

---

## Klíčová designová rozhodnutí

1. **Hybridní vyhledávání**: Kombinace vektorové podobnosti (60%) s BM25 keyword matchingem (40%) zajišťuje jak sémantické porozumění, tak přesné párování termínů.

2. **Rozšíření dotazu**: Podpora českého jazyka se synonymy a variantami lokalit zlepšuje recall pro lokální vyhledávání.

3. **Detekce regionů**: Automatická normalizace regionů ČR (Praha, Morava, atd.) umožňuje přesné filtrování podle geografické oblasti.

4. **Dual-database architektura**: SQLite pro transakční data (leads, konverzace), ChromaDB pro vektorové vyhledávání - optimální kombinace pro různé typy dotazů.

5. **LLM přeřazení**: Finální průchod s GPT zajišťuje správné vážení business priorit (featured nabídky, exact matches).

6. **Fázově orientované konverzace**: 7 odlišných fází (uvítání → předání) umožňuje kontextově vhodné odpovědi.

7. **Vícefaktorový scoring**: 4-komponentní lead scoring poskytuje transparentní, vysvětlitelnou kvalifikaci.

---

## Fáze konverzace

| Fáze | Název | Popis |
|------|-------|-------|
| 1 | `greeting` | Uvítání a úvodní dotaz |
| 2 | `needs_discovery` | Zjišťování požadavků klienta |
| 3 | `property_search` | Vyhledávání odpovídajících nemovitostí |
| 4 | `recommendation` | Prezentace nejlepších shod |
| 5 | `objection_handling` | Řešení námitek |
| 6 | `contact_capture` | Získání kontaktních údajů |
| 7 | `handoff` | Příprava souhrnu pro makléře |

---

## Typy zákazníků

| Typ | Popis | Přístup |
|-----|-------|---------|
| **INFORMED** | Má jasné požadavky, realistické | Přímé doporučení |
| **VAGUE** | Nejasné požadavky, potřebuje upřesnit | Kvalifikační otázky |
| **UNREALISTIC** | Požadavky mimo tržní realitu | Vysvětlení trhu, alternativy |
