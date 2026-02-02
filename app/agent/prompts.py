"""
Prompt Templates for the Real Estate Agent.

Optimized for token efficiency while maintaining behavior quality.
"""

# Main system prompt (~800 tokens, reduced from ~1200)
SYSTEM_PROMPT = """Jsi PETRA, AI asistentka realitní kanceláře PROCHAZKA REALITY, specialista na komerční nemovitosti v ČR (sklady a kanceláře).

## ZÁKLADNÍ PRAVIDLA
1. HNED HLEDEJ - Jakékoliv info (typ/lokalita/plocha) → search_properties()
2. VŽDY ALTERNATIVY - Není přesná shoda? Ukaž nejbližší + vysvětli rozdíly
3. MAX 2 OTÁZKY - Neptej se na vše najednou
4. KONTAKT NA KONEC - Nejdřív hodnota (nemovitosti), pak kontakt
5. BUĎ KONZULTANT - Přátelsky, ne výslechově

## POSTUP KONVERZACE
1. Uvítání (krátké)
2. Zjisti co hledá (1 otázka)
3. IHNED VYHLEDEJ a ukaž nemovitosti
4. Upřesni dle reakce
5. Doporuč nejlepší shodu
6. Nabídni prohlídku/kontakt

## KDY NENÍ SHODA
1. KOMBINACE: "Mám dva sklady blízko sebe - 800m² a 1200m², celkem 2000m²"
2. NOTIFIKACE: "Mohu vás informovat, až se objeví nová nabídka"
3. MAKLÉŘ: "Mohu vás spojit s makléřem pro nestandardní řešení"

## SBĚR KONTAKTŮ (postupně)
1. Email: "Na jaký email vám mám poslat info?"
2. Jméno: "Jak vám mohu říkat?"
3. Preference: "Vyhovuje email, nebo preferujete telefon?"
4. Telefon: (jen pokud preferuje) "Jaké je vaše číslo?"
5. Schůzka: "Chcete naplánovat schůzku s makléřem?"

## NÁSTROJE (kdy použít)
- search_properties: Při každém dotazu na nemovitost
- register_property_alert: Když klient chce notifikace + má email
- schedule_broker_contact: Když chce mluvit s makléřem
- get_market_overview: Když se ptá na ceny/trh

## ZOBRAZENÍ VÝSLEDKŮ
- Ukaž TOP 3, pak "Mám další možnosti..."
- Zachovej obrázky pokud jsou
- Přidej odkaz na mapu: [Zobrazit na mapě](https://www.google.com/maps/search/LOKACE)

## ZÁKAZY
- NIKDY neříkej "nemáme nic" bez alternativ
- NIKDY neopakuj otázky na info které už máš
- NIKDY nežádej kontakt jako první věc
- NIKDY více než 2 otázky najednou

## EMOCE
- Frustrovaný klient: "Rozumím, že je to náročné. Pojďme to zkusit jinak..."
- Nerozhodný: "Není kam spěchat. Co kdybychom zúžili možnosti?"
- Nerealistické očekávání: Vysvětli trh, nabídni alternativy

## MIMO ROZSAH
- Rezidenční: "Specializujeme se na komerční prostory. Pro byty doporučuji Sreality.cz"
- Osobní otázky: "Jsem AI asistent, zaměřuji se na pomoc s nemovitostmi."
"""

# Dynamic context template - injected before each response
CONTEXT_TEMPLATE = """
## UŽ ZNÁME (NEPTAT SE ZNOVU!)
{collected_info}

## JEŠTĚ NEZNÁME (lze se zeptat)
{missing_info}

## FÁZE: {phase}
{phase_instructions}

{conversation_summary}"""

# Checklist fields for lead info
LEAD_CHECKLIST = {
    "property_type": "Typ nemovitosti",
    "area": "Požadovaná plocha",
    "locations": "Preferované lokality",
    "budget": "Rozpočet",
    "urgency": "Časový horizont",
    "name": "Jméno klienta",
    "email": "Email",
    "phone": "Telefon",
    "company": "Firma",
}

# Phase-specific instructions
PHASE_INSTRUCTIONS = {
    "greeting": "Přivítej klienta a zjisti co hledá (1 otázka max). Buď přátelský a vstřícný.",
    "needs_discovery": "Vyhledej nemovitosti na základě dosavadních info. Ukazuj výsledky, ne otázky.",
    "property_search": "Ukaž výsledky, zeptej se na reakci. 'Co říkáte na tyto možnosti?'",
    "recommendation": "Doporuč nejlepší shodu, vysvětli proč. 'Nejvíce vám odpovídá...'",
    "objection_handling": "Adresuj námitky, nabídni alternativy. Buď empatický.",
    "contact_capture": "Nabídni prohlídku, získej kontakt. 'Chcete si nemovitost prohlédnout?'",
    "handoff": "Potvrď schůzku, shrň další kroky. Buď profesionální.",
}

# Optimized extraction prompt with intent classification
EXTRACTION_PROMPT = """Analyzuj zprávu klienta realitní kanceláře.

ZPRÁVA: {message}
STÁVAJÍCÍ DATA: {current_info}

Úkoly:
1. INTENT: Urči záměr zprávy
2. EXTRAKCE: Pouze NOVÉ informace (ne opakování stávajících)
3. KOREKCE: Pokud zpráva opravuje předchozí info

Odpověz jako JSON:
{{
  "intent": "info|question|request|ack|objection",
  "has_new_info": true/false,
  "extracted": {{
    "property_type": null | "warehouse" | "office",
    "min_area_sqm": null | number,
    "max_area_sqm": null | number,
    "locations": [],
    "max_price_czk_sqm": null | number,
    "move_in_urgency": null | "immediate" | "1-3months" | "3-6months" | "flexible",
    "name": null | string,
    "email": null | string (musí obsahovat @),
    "phone": null | string (9 číslic),
    "company": null | string,
    "preferred_contact_method": null | "email" | "phone" | "sms",
    "wants_notifications": null | true,
    "wants_broker_contact": null | true
  }},
  "corrections": {{}},
  "detected_objection": null | string
}}"""

# Search decision prompt (simplified)
SEARCH_DECISION_PROMPT = """Máme dostatek info pro vyhledání?

Požadavky: Typ={property_type}, Plocha={area}, Lokalita={locations}, Rozpočet={budget}

Minimum: typ NEBO (plocha/lokalita/rozpočet)

Odpověz: ANO/NE"""

# Structured summary prompt
SUMMARY_PROMPT = """Shrň konverzaci pro makléře (max 150 slov).

KONVERZACE:
{messages}

Struktura:
1. POŽADAVKY (1-2 věty): typ, velikost, lokalita, rozpočet
2. KLÍČOVÉ BODY (2-3 body): co je důležité, dotazy, obavy
3. PŘEKÁŽKY (pokud byly): cenové, časové, lokační
4. DOPORUČENÝ DALŠÍ KROK: co by měl makléř udělat

Odpověz stručně v češtině."""

# Reranker prompt with business priority
RERANKER_PROMPT = """Ohodnoť nemovitosti podle relevance pro klienta (1-10).

DOTAZ: "{query}"
POŽADAVKY: {requirements}

NEMOVITOSTI:
{properties}

FAKTORY (váhy):
- Shoda typu: 25%
- Vhodnost lokality: 25%
- Adekvát velikosti: 20%
- Cenová dostupnost: 20%
- Dostupnost ihned: 10%

BONUS:
- is_hot/is_featured: +0.5 bodu
- Přesná shoda všech kritérií: +1 bod

Odpověz JSON: [{{"index": 1, "score": 8.5, "reason": "..."}}]"""


# Intent classification patterns (for fast pre-filtering)
INTENT_PATTERNS = {
    "ack": [
        "ok", "ano", "díky", "dobře", "rozumím", "jasně", "jo", "super",
        "fajn", "paráda", "skvěle", "v pohodě", "jasný", "chápu"
    ],
    "question": ["?", "jak", "kde", "kdy", "kolik", "proč", "jaký", "co je"],
    "request": ["chci", "potřebuji", "hledám", "ukažte", "dejte", "pošlete", "najděte"],
    "objection": ["drahé", "malé", "velké", "daleko", "ne ", "nechci", "moc", "málo"],
    "contact": ["email", "telefon", "@", "+420", "zavolejte", "mail"],
    "greeting": ["dobrý den", "ahoj", "čau", "zdravím", "nazdar"],
}

# Quick responses for acknowledgments (skip LLM)
QUICK_RESPONSES = {
    "ack_search": "Výborně! Hned vyhledám další možnosti...",
    "ack_continue": "Rozumím. Je ještě něco, co bych vám mohla pomoct najít?",
    "ack_contact": "Děkuji za informace. Ozvu se vám co nejdříve.",
}


def classify_intent(message: str) -> str:
    """
    Classify message intent using pattern matching.

    Returns one of: ack, question, request, objection, contact, greeting, info
    """
    message_lower = message.lower().strip()

    # Check for pure acknowledgments first
    if message_lower in INTENT_PATTERNS["ack"] or len(message_lower) < 5:
        return "ack"

    # Check for greeting
    for pattern in INTENT_PATTERNS["greeting"]:
        if message_lower.startswith(pattern):
            return "greeting"

    # Check other patterns
    for intent, patterns in INTENT_PATTERNS.items():
        if intent in ["ack", "greeting"]:
            continue
        for pattern in patterns:
            if pattern in message_lower:
                return intent

    return "info"  # Default: providing information


def should_extract(message: str) -> bool:
    """
    Determine if message likely contains extractable information.

    Returns False for short acknowledgments to save LLM calls.
    """
    import re

    message_lower = message.lower().strip()

    # Skip very short messages
    if len(message_lower) < 5:
        return False

    # Skip pure acknowledgments
    if message_lower in INTENT_PATTERNS["ack"]:
        return False

    # Check for info patterns that warrant extraction
    info_patterns = [
        r'\d+',  # Numbers (area, price, phone)
        r'@',  # Email
        r'sklad|kancel|office|warehouse|kancl',  # Property type
        r'praha|brno|ostrava|plzen|olomouc|morav|čech|liberec|hradec|kladno',  # Locations & regions
        r'm[²2]|metru|metr',  # Area mentions
        r'kc|korun|czk',  # Price mentions
        r'ihned|mesic|rok',  # Urgency
        r'email|telefon|mail|volat',  # Contact info
        r'velk|střed|mal|open.?space|call.?cent',  # Size/type descriptors
    ]

    for pattern in info_patterns:
        if re.search(pattern, message_lower):
            return True

    # If message is long enough, extract anyway
    return len(message_lower) > 50


def build_context_prompt(lead, phase: str, conversation_summary: str = "") -> str:
    """
    Build dynamic context with clear checklist of collected vs missing info.

    Args:
        lead: Current Lead model
        phase: Current conversation phase
        conversation_summary: Optional summary of older conversation

    Returns:
        Formatted context string
    """
    collected = []
    missing = []

    # Property type
    if lead.property_type:
        ptype = "sklad" if lead.property_type == "warehouse" else "kancelář"
        collected.append(f"✓ Typ: {ptype}")
    else:
        missing.append("- Typ nemovitosti (sklad/kancelář)")

    # Area
    if lead.min_area_sqm or lead.max_area_sqm:
        if lead.min_area_sqm and lead.max_area_sqm:
            collected.append(f"✓ Plocha: {lead.min_area_sqm}-{lead.max_area_sqm} m²")
        elif lead.min_area_sqm:
            collected.append(f"✓ Plocha: min. {lead.min_area_sqm} m²")
        else:
            collected.append(f"✓ Plocha: max. {lead.max_area_sqm} m²")
    else:
        missing.append("- Požadovaná plocha")

    # Locations
    if lead.preferred_locations:
        collected.append(f"✓ Lokality: {', '.join(lead.preferred_locations)}")
    else:
        missing.append("- Preferované lokality")

    # Budget
    if lead.max_price_czk_sqm:
        collected.append(f"✓ Rozpočet: max. {lead.max_price_czk_sqm} Kč/m²")
    else:
        missing.append("- Rozpočet (nepovinné)")

    # Urgency
    urgency_map = {
        "immediate": "ihned",
        "1-3months": "1-3 měsíce",
        "3-6months": "3-6 měsíců",
        "flexible": "flexibilní",
    }
    if lead.move_in_urgency:
        collected.append(f"✓ Nástup: {urgency_map.get(lead.move_in_urgency, lead.move_in_urgency)}")

    # Contact info
    if lead.name:
        collected.append(f"✓ Jméno: {lead.name}")
    else:
        missing.append("- Jméno (až po ukázání nemovitostí)")

    if lead.email:
        collected.append(f"✓ Email: {lead.email}")
    else:
        missing.append("- Email (až po ukázání nemovitostí)")

    if lead.phone:
        collected.append(f"✓ Telefon: {lead.phone}")

    if lead.company:
        collected.append(f"✓ Firma: {lead.company}")

    # Format collected and missing
    collected_str = "\n".join(collected) if collected else "(zatím nic)"
    missing_str = "\n".join(missing) if missing else "(vše zjištěno)"

    # Phase instructions
    phase_instructions = PHASE_INSTRUCTIONS.get(phase, PHASE_INSTRUCTIONS["needs_discovery"])

    # Conversation summary section
    summary_section = ""
    if conversation_summary:
        summary_section = f"\n## SOUHRN PŘEDCHOZÍ KONVERZACE\n{conversation_summary}"

    return CONTEXT_TEMPLATE.format(
        collected_info=collected_str,
        missing_info=missing_str,
        phase=phase,
        phase_instructions=phase_instructions,
        conversation_summary=summary_section,
    )


def get_full_system_prompt(
    lead=None,
    phase: str = "greeting",
    conversation_summary: str = "",
) -> str:
    """
    Get full system prompt with dynamic context.

    Args:
        lead: Optional Lead model for context
        phase: Current conversation phase
        conversation_summary: Optional summary of older messages

    Returns:
        Complete system prompt
    """
    if lead is None:
        return SYSTEM_PROMPT

    context = build_context_prompt(lead, phase, conversation_summary)
    return SYSTEM_PROMPT + "\n" + context


# Conversation summary prompt (for incremental summarization)
CONVERSATION_SUMMARY_PROMPT = """Shrň tuto část konverzace do 2-3 vět. Zachovej:
- Klíčové požadavky klienta
- Nemovitosti které byly ukázány/diskutovány
- Důležité reakce klienta (co se líbilo/nelíbilo)

KONVERZACE:
{messages}

Odpověz stručně v češtině (max 100 slov):"""
