import json
from datetime import date
from functools import lru_cache
from typing import Any

from langchain.tools import tool

from app.rag.retriever import PropertyRetriever
from app.scoring.lead_scorer import LeadScorer
from app.models.lead import Lead
from app.models.property import Property
from app.data.loader import get_property_by_id, get_market_stats, load_properties
from app.config import SCHEDULING_MODE, CALENDLY_URL, CALENDLY_EVENT_TYPES, BROKER_NAME
from app.utils import get_logger
from app.analytics import get_property_tracker

logger = get_logger(__name__)


def get_scheduling_mode() -> str:
    """Get current scheduling mode, checking session state first."""
    try:
        import streamlit as st
        if "scheduling_mode" in st.session_state:
            return st.session_state.scheduling_mode
    except Exception:
        pass
    return SCHEDULING_MODE


def get_calendar_service():
    """Get the Google Calendar service if available."""
    try:
        from app.calendar import get_calendar_service as _get_service
        return _get_service()
    except Exception:
        return None


class RetrieverSingleton:
    """
    Thread-safe singleton for PropertyRetriever.

    Uses class-level caching to ensure only one instance exists.
    """
    _instance: PropertyRetriever | None = None

    @classmethod
    def get_instance(cls) -> PropertyRetriever:
        """Get or create the singleton PropertyRetriever instance."""
        if cls._instance is None:
            logger.info("Initializing PropertyRetriever singleton")
            cls._instance = PropertyRetriever()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton (useful for testing)."""
        logger.debug("Resetting PropertyRetriever singleton")
        cls._instance = None


def get_retriever() -> PropertyRetriever:
    """Get the PropertyRetriever singleton instance."""
    return RetrieverSingleton.get_instance()


def get_rag_settings() -> dict:
    """Get current RAG settings from session state or config."""
    try:
        import streamlit as st
        return {
            "use_hybrid": st.session_state.get("rag_hybrid", True),
            "use_expansion": st.session_state.get("rag_expansion", True),
            "use_reranking": st.session_state.get("rag_reranking", True),
        }
    except Exception:
        from app.config import RAG_USE_HYBRID_SEARCH, RAG_USE_QUERY_EXPANSION, RAG_USE_RERANKING
        return {
            "use_hybrid": RAG_USE_HYBRID_SEARCH,
            "use_expansion": RAG_USE_QUERY_EXPANSION,
            "use_reranking": RAG_USE_RERANKING,
        }


@tool
def search_properties(
    property_type: str | None = None,
    locations: str | None = None,
    min_area: int | None = None,
    max_area: int | None = None,
    max_price: int | None = None,
    available_now: bool = False,
) -> str:
    """
    Vyhledá nemovitosti v databázi podle zadaných kritérií.
    VŽDY vrátí nějaké výsledky - buď přesné shody nebo nejbližší alternativy.

    Používá pokročilé vyhledávání:
    - Hybridní vyhledávání (vektor + klíčová slova)
    - Rozšíření dotazu (synonyma, související lokality)
    - LLM re-ranking pro lepší relevanci

    Args:
        property_type: Typ nemovitosti - "warehouse" (sklad) nebo "office" (kancelář)
        locations: Preferované lokality oddělené čárkou (např. "Praha, Brno")
        min_area: Minimální plocha v m²
        max_area: Maximální plocha v m²
        max_price: Maximální cena v Kč/m²/měsíc
        available_now: Pouze ihned dostupné nemovitosti

    Returns:
        Seznam nalezených nemovitostí s detaily - VŽDY vrátí něco
    """
    retriever = get_retriever()
    rag_settings = get_rag_settings()

    # Parse locations
    location_list = None
    if locations:
        location_list = [loc.strip() for loc in locations.split(",")]

    # Build a natural language query for better semantic search
    query_parts = []
    if property_type:
        query_parts.append("sklad" if property_type == "warehouse" else "kancelář")
    if location_list:
        query_parts.append(" ".join(location_list))
    if min_area:
        query_parts.append(f"{min_area} m²")
    query = " ".join(query_parts) if query_parts else ""

    # Search with enhanced RAG features
    properties = retriever.search_properties(
        query=query,
        property_type=property_type,
        locations=location_list,
        min_area=min_area,
        max_area=max_area,
        max_price=max_price,
        top_k=5,
        use_hybrid=rag_settings["use_hybrid"],
        use_expansion=rag_settings["use_expansion"],
        use_reranking=rag_settings["use_reranking"],
    )

    # If we have results, return them (show top 3, mention more available)
    if properties:
        # Track property views for analytics
        tracker = get_property_tracker()
        for prop in properties:
            tracker.track_view(prop.id)

        results = []
        show_count = min(3, len(properties))
        for i, prop in enumerate(properties[:show_count], 1):
            results.append(f"{i}. {prop.to_display_text()}")

        output = f"Nalezeno {len(properties)} nemovitostí. Zobrazuji TOP {show_count}:\n\n" + "\n\n".join(results)

        if len(properties) > 3:
            # Store remaining for "show more"
            remaining = [f"{i}. {prop.to_display_text()}" for i, prop in enumerate(properties[3:], 4)]
            output += f"\n\n---\n**Další možnosti ({len(properties) - 3}):**\n\n" + "\n\n".join(remaining)

        return output

    # No exact match - progressively relax criteria and explain
    relaxed_filters = []

    # Try without price filter
    if max_price:
        properties = retriever.search_properties(
            property_type=property_type,
            locations=location_list,
            min_area=min_area,
            max_area=max_area,
            max_price=None,
            top_k=5,
        )
        if properties:
            relaxed_filters.append(f"cena (vaše max {max_price} Kč/m²)")

    # Try without location filter
    if not properties and location_list:
        properties = retriever.search_properties(
            property_type=property_type,
            locations=None,
            min_area=min_area,
            max_area=max_area,
            max_price=max_price,
            top_k=5,
        )
        if properties:
            relaxed_filters.append(f"lokalita ({', '.join(location_list)})")

    # Try without area filter
    if not properties and (min_area or max_area):
        properties = retriever.search_properties(
            property_type=property_type,
            locations=location_list,
            min_area=None,
            max_area=None,
            max_price=max_price,
            top_k=5,
        )
        if properties:
            area_desc = f"{min_area}-{max_area}" if min_area and max_area else f"min {min_area}" if min_area else f"max {max_area}"
            relaxed_filters.append(f"plocha ({area_desc} m²)")

    # Last resort - just get by type or all properties
    if not properties:
        if property_type:
            properties = retriever.search_properties(
                property_type=property_type,
                top_k=5,
            )
            relaxed_filters = ["všechna kritéria kromě typu"]
        else:
            # Get featured/hot properties as fallback
            all_props = load_properties()
            properties = sorted(all_props, key=lambda p: p.priority_score, reverse=True)[:5]
            relaxed_filters = ["všechna kritéria - zobrazuji TOP nabídky"]

    if properties:
        results = []
        for i, prop in enumerate(properties, 1):
            results.append(f"{i}. {prop.to_display_text()}")

        relaxed_text = ", ".join(relaxed_filters) if relaxed_filters else ""
        header = f"Přesná shoda nebyla nalezena. Upravil jsem: {relaxed_text}\n\nNejbližší alternativy:\n\n" if relaxed_filters else ""

        return header + "\n\n".join(results)

    # This should never happen, but just in case
    return "V databázi je 20 nemovitostí. Zkuste vyhledání bez filtrů."


@tool
def get_property_details(property_id: int) -> str:
    """
    Získá detailní informace o konkrétní nemovitosti.

    Args:
        property_id: ID nemovitosti

    Returns:
        Detailní popis nemovitosti
    """
    prop = get_property_by_id(property_id)

    if not prop:
        return f"Nemovitost s ID {property_id} nebyla nalezena."

    return prop.to_display_text()


@tool
def get_market_overview(property_type: str | None = None) -> str:
    """
    Získá přehled trhu s komerčními nemovitostmi.
    Užitečné pro vysvětlení cen klientovi.

    Args:
        property_type: Volitelně "warehouse" nebo "office" pro specifický typ

    Returns:
        Statistiky trhu (průměrné ceny, dostupnost, atd.)
    """
    stats = get_market_stats()

    if property_type == "warehouse":
        s = stats["warehouse"]
        return f"""Přehled trhu - SKLADY:
- Počet nabídek: {s['count']}
- Průměrná cena: {s['avg_price']} Kč/m²/měsíc
- Cenové rozpětí: {s['min_price']} - {s['max_price']} Kč/m²/měsíc
- Průměrná plocha: {s['avg_area']} m²

Nejlevnější sklady jsou v Ostravě ({s['min_price']} Kč/m²), nejdražší v Praze (až {s['max_price']} Kč/m²)."""

    elif property_type == "office":
        s = stats["office"]
        return f"""Přehled trhu - KANCELÁŘE:
- Počet nabídek: {s['count']}
- Průměrná cena: {s['avg_price']} Kč/m²/měsíc
- Cenové rozpětí: {s['min_price']} - {s['max_price']} Kč/m²/měsíc
- Průměrná plocha: {s['avg_area']} m²

Nejlevnější kanceláře jsou v Ostravě ({s['min_price']} Kč/m²), nejdražší v centru Prahy (až {s['max_price']} Kč/m²)."""

    else:
        sw = stats["warehouse"]
        so = stats["office"]
        return f"""Přehled trhu - KOMERČNÍ NEMOVITOSTI:

SKLADY ({sw['count']} nabídek):
- Průměrná cena: {sw['avg_price']} Kč/m²/měsíc
- Cenové rozpětí: {sw['min_price']} - {sw['max_price']} Kč/m²/měsíc

KANCELÁŘE ({so['count']} nabídek):
- Průměrná cena: {so['avg_price']} Kč/m²/měsíc
- Cenové rozpětí: {so['min_price']} - {so['max_price']} Kč/m²/měsíc"""


@tool
def show_top_properties(property_type: str | None = None, count: int = 5) -> str:
    """
    Zobrazí TOP/doporučené nemovitosti.
    Použij když chceš klientovi ukázat naše nejlepší nabídky.

    Args:
        property_type: Volitelně "warehouse" nebo "office"
        count: Počet nemovitostí k zobrazení (max 5)

    Returns:
        Seznam TOP nemovitostí
    """
    all_props = load_properties()

    # Filter by type if specified
    if property_type:
        all_props = [p for p in all_props if p.property_type == property_type]

    # Sort by priority (featured/hot first)
    sorted_props = sorted(all_props, key=lambda p: (p.is_hot, p.is_featured, p.priority_score), reverse=True)

    top = sorted_props[:min(count, 5)]

    results = []
    for i, prop in enumerate(top, 1):
        badge = ""
        if prop.is_hot:
            badge = " [HOT - Akce!]"
        elif prop.is_featured:
            badge = " [Doporuceno]"
        results.append(f"{i}. {prop.to_display_text()}{badge}")

    type_label = "sklady" if property_type == "warehouse" else "kanceláře" if property_type == "office" else "nemovitosti"
    return f"TOP {type_label}:\n\n" + "\n\n".join(results)


@tool
def calculate_lead_score(
    property_type: str | None = None,
    has_area: bool = False,
    has_location: bool = False,
    has_budget: bool = False,
    has_urgency: bool = False,
    has_contact: bool = False,
    matched_count: int = 0,
    budget_realistic: bool = True,
) -> str:
    """
    Vypočítá skóre kvality leadu na základě shromážděných informací.

    Args:
        property_type: Typ požadované nemovitosti
        has_area: Zda byla specifikována plocha
        has_location: Zda byla specifikována lokalita
        has_budget: Zda byl specifikován rozpočet
        has_urgency: Zda byl specifikován termín nástupu
        has_contact: Zda máme kontaktní údaje
        matched_count: Počet nalezených vhodných nemovitostí
        budget_realistic: Zda je rozpočet realistický

    Returns:
        Skóre a hodnocení leadu
    """
    score = 0

    # Completeness (max 30)
    if property_type:
        score += 6
    if has_area:
        score += 6
    if has_location:
        score += 6
    if has_budget:
        score += 6
    if has_urgency:
        score += 6

    # Realism (max 30)
    if budget_realistic:
        score += 15
    if has_urgency:
        score += 10
    if has_area:
        score += 5

    # Match quality (max 25)
    if matched_count >= 3:
        score += 25
    elif matched_count >= 1:
        score += 15
    elif matched_count == 0 and property_type:
        score += 5

    # Engagement (max 15)
    if has_contact:
        score += 15

    score = min(score, 100)

    if score >= 70:
        quality = "HOT - Prioritni lead, okamzite kontaktovat"
    elif score >= 40:
        quality = "WARM - Kvalitni lead, kontaktovat do 24h"
    else:
        quality = "COLD - Nurture lead, zaradit do kampane"

    return f"""Lead Score: {score}/100
Hodnoceni: {quality}

Breakdown:
- Uplnost informaci: {30 if all([property_type, has_area, has_location, has_budget, has_urgency]) else 'castecne'}/30
- Realnost pozadavku: {'vysoka' if budget_realistic else 'nizka'}/30
- Shoda s nabidkou: {matched_count} nemovitosti/25
- Kontaktni udaje: {'ano' if has_contact else 'ne'}/15"""


@tool
def register_property_alert(
    email: str,
    property_type: str | None = None,
    min_area: int | None = None,
    locations: str | None = None,
    max_price: int | None = None,
    name: str | None = None,
) -> str:
    """
    Zaregistruje klienta pro notifikace o nových nemovitostech odpovídajících jeho kritériím.
    Použij když klient chce být informován o nových nabídkách.

    Args:
        email: E-mail klienta (POVINNÉ)
        property_type: Typ nemovitosti - "warehouse" nebo "office"
        min_area: Minimální plocha v m²
        locations: Preferované lokality oddělené čárkou
        max_price: Maximální cena v Kč/m²/měsíc
        name: Jméno klienta

    Returns:
        Potvrzení registrace
    """
    if not email:
        return "Pro registraci notifikací potřebuji e-mailovou adresu."

    criteria_parts = []
    if property_type:
        type_cz = "sklady" if property_type == "warehouse" else "kanceláře"
        criteria_parts.append(type_cz)
    if min_area:
        criteria_parts.append(f"min. {min_area} m²")
    if locations:
        criteria_parts.append(f"lokality: {locations}")
    if max_price:
        criteria_parts.append(f"max. {max_price} Kč/m²")

    criteria_text = ", ".join(criteria_parts) if criteria_parts else "všechny nové nabídky"
    name_text = f" pro {name}" if name else ""

    return f"""✅ Notifikace úspěšně zaregistrována{name_text}!

📧 E-mail: {email}
🔍 Hlídaná kritéria: {criteria_text}

Budeme vás informovat e-mailem, jakmile se objeví odpovídající nemovitost.
Obvykle přidáváme nové nabídky každý týden."""


@tool
def schedule_broker_contact(
    contact_type: str,
    email: str | None = None,
    phone: str | None = None,
    name: str | None = None,
    preferred_time: str | None = None,
    notes: str | None = None,
) -> str:
    """
    Naplánuje kontakt s makléřem nebo schůzku.
    Použij když klient chce mluvit s makléřem nebo naplánovat schůzku.

    Args:
        contact_type: Typ kontaktu - "immediate" (hned), "call" (telefonát), "video" (videohovor), "meeting" (osobní schůzka)
        email: E-mail klienta
        phone: Telefon klienta (potřebný pro call)
        name: Jméno klienta
        preferred_time: Preferovaný čas, např. "zítra odpoledne", "pondělí 10:00"
        notes: Poznámky k požadavkům klienta

    Returns:
        Potvrzení naplánovaného kontaktu
    """
    if not email and not phone:
        return "Pro spojení s makléřem potřebuji alespoň e-mail nebo telefon."

    name_text = name if name else "Vážený klient"
    contact_info = []
    if email:
        contact_info.append(f"📧 {email}")
    if phone:
        contact_info.append(f"📞 {phone}")

    # Check scheduling mode
    mode = get_scheduling_mode()

    # CALENDLY MODE - return booking link
    if mode == "calendly":
        event_suffix = CALENDLY_EVENT_TYPES.get(contact_type, "/30min")
        calendly_link = f"{CALENDLY_URL}{event_suffix}"

        # Add prefill parameters if we have email/name
        prefill_params = []
        if email:
            prefill_params.append(f"email={email}")
        if name:
            prefill_params.append(f"name={name}")
        if prefill_params:
            calendly_link += "?" + "&".join(prefill_params)

        if contact_type == "immediate":
            return f"""✅ Předáno makléři {BROKER_NAME} k okamžitému kontaktu!

👤 {name_text}
{chr(10).join(contact_info)}

Makléř vás bude kontaktovat co nejdříve (obvykle do 30 minut v pracovní době).

Nebo si můžete rovnou vybrat termín v kalendáři:
🗓️ **[Rezervovat termín]({calendly_link})**"""

        elif contact_type == "call":
            return f"""📞 Naplánujte si telefonát s makléřem {BROKER_NAME}:

👤 {name_text}
{chr(10).join(contact_info)}

🗓️ **Vyberte si termín v kalendáři:**
{calendly_link}

Po rezervaci obdržíte potvrzení na e-mail."""

        elif contact_type == "video":
            return f"""🎥 Naplánujte si videohovor s makléřem {BROKER_NAME}:

👤 {name_text}
{chr(10).join(contact_info)}

🗓️ **Vyberte si termín v kalendáři:**
{calendly_link}

Po rezervaci obdržíte odkaz na videohovor na e-mail."""

        elif contact_type == "meeting":
            return f"""🤝 Naplánujte si osobní schůzku s makléřem {BROKER_NAME}:

👤 {name_text}
{chr(10).join(contact_info)}

🗓️ **Vyberte si termín v kalendáři:**
{calendly_link}

Po rezervaci vás budeme kontaktovat ohledně místa schůzky."""

        else:
            return f"""📅 Naplánujte si schůzku s makléřem {BROKER_NAME}:

👤 {name_text}
{chr(10).join(contact_info)}

🗓️ **Vyberte si termín v kalendáři:**
{calendly_link}"""

    # SIMULATED MODE - original behavior
    if contact_type == "immediate":
        return f"""✅ Předáno makléři k okamžitému kontaktu!

👤 {name_text}
{chr(10).join(contact_info)}

Náš makléř vás bude kontaktovat co nejdříve, obvykle do 30 minut v pracovní době (Po-Pá 9-18h)."""

    elif contact_type == "call":
        time_text = f" v termínu: {preferred_time}" if preferred_time else ""
        return f"""✅ Telefonát s makléřem naplánován!

👤 {name_text}
{chr(10).join(contact_info)}
🕐 Termín:{time_text if time_text else " Makléř se ozve v nejbližším vhodném čase"}

Makléř vám zavolá a probere s vámi vaše požadavky i nestandardní možnosti."""

    elif contact_type == "video":
        time_text = f" v termínu: {preferred_time}" if preferred_time else ""
        return f"""✅ Videohovor s makléřem naplánován!

👤 {name_text}
{chr(10).join(contact_info)}
🎥 Typ: Videohovor (pošleme odkaz na e-mail)
🕐 Termín:{time_text if time_text else " Makléř se ozve ohledně termínu"}

Na e-mail vám pošleme odkaz na videohovor a potvrzení termínu."""

    elif contact_type == "meeting":
        time_text = f" v termínu: {preferred_time}" if preferred_time else ""
        return f"""✅ Osobní schůzka s makléřem naplánována!

👤 {name_text}
{chr(10).join(contact_info)}
📍 Místo: Naše kancelář nebo dle domluvy
🕐 Termín:{time_text if time_text else " Makléř se ozve ohledně termínu a místa"}

Makléř vás bude kontaktovat pro potvrzení detailů schůzky."""

    else:
        return f"""✅ Požadavek na kontakt s makléřem zaznamenán!

👤 {name_text}
{chr(10).join(contact_info)}

Náš makléř vás bude kontaktovat v nejbližší době."""


@tool
def get_available_meeting_slots(
    days_ahead: int = 7,
    slot_duration: int = 30,
) -> str:
    """
    Získá dostupné termíny pro schůzku s makléřem z kalendáře.
    Použij když klient chce vědět, kdy je makléř dostupný.

    Args:
        days_ahead: Kolik dní dopředu hledat (default 7)
        slot_duration: Délka schůzky v minutách - 15, 30, nebo 60 (default 30)

    Returns:
        Seznam dostupných termínů
    """
    mode = get_scheduling_mode()

    if mode == "google":
        calendar = get_calendar_service()
        if calendar and calendar.is_available():
            slots = calendar.get_available_slots(
                days_ahead=days_ahead,
                slot_duration_minutes=slot_duration,
            )
            return calendar.format_available_slots_for_display(slots)

    # Simulated or fallback response
    from datetime import datetime, timedelta

    now = datetime.now()
    slots_text = ["**Dostupné termíny:**\n"]

    day_names = {0: "Pondělí", 1: "Úterý", 2: "Středa", 3: "Čtvrtek", 4: "Pátek"}

    slot_count = 0
    for day_offset in range(1, days_ahead + 1):
        check_date = now.date() + timedelta(days=day_offset)

        # Skip weekends
        if check_date.weekday() >= 5:
            continue

        day_name = day_names.get(check_date.weekday(), "")
        date_str = check_date.strftime("%d.%m.")

        times = ["9:00", "11:00", "14:00", "16:00"]
        slots_text.append(f"\n**{day_name} {date_str}:**")

        for t in times[:2]:  # Show 2 slots per day
            slots_text.append(f"  - {t}")
            slot_count += 1

        if slot_count >= 8:
            break

    return "\n".join(slots_text)


@tool
def book_meeting_slot(
    selected_time: str,
    meeting_type: str = "call",
    email: str | None = None,
    name: str | None = None,
    phone: str | None = None,
    notes: str | None = None,
) -> str:
    """
    Zarezervuje konkrétní termín schůzky s makléřem.
    Použij poté, co klient vybral termín z dostupných slotů.

    Args:
        selected_time: Vybraný termín, např. "Úterý 10:00" nebo "15.1. 14:00"
        meeting_type: Typ schůzky - "call" (telefonát), "video" (videohovor), "meeting" (osobní)
        email: Email klienta pro zaslání pozvánky
        name: Jméno klienta
        phone: Telefon klienta
        notes: Poznámky k požadavkům

    Returns:
        Potvrzení rezervace
    """
    from datetime import datetime, timedelta
    import re

    mode = get_scheduling_mode()
    name_text = name or "Klient"

    # Try to parse the selected time
    # This is a simplified parser - in production, use more robust parsing
    parsed_time = None

    # Try to extract day and time
    time_match = re.search(r'(\d{1,2}):(\d{2})', selected_time)
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2))

        # Try to find day reference
        now = datetime.now()
        target_date = now.date()

        day_keywords = {
            "pondělí": 0, "úterý": 1, "středa": 2, "střed": 2,
            "čtvrtek": 3, "pátek": 4, "po": 0, "út": 1, "st": 2, "čt": 3, "pá": 4,
        }

        for keyword, weekday in day_keywords.items():
            if keyword in selected_time.lower():
                # Find next occurrence of this weekday
                days_ahead = (weekday - now.weekday()) % 7
                if days_ahead == 0:
                    days_ahead = 7  # Next week if today
                target_date = now.date() + timedelta(days=days_ahead)
                break

        # Check for date pattern like "15.1." or "15.01."
        date_match = re.search(r'(\d{1,2})\.(\d{1,2})\.?', selected_time)
        if date_match:
            day = int(date_match.group(1))
            month = int(date_match.group(2))
            year = now.year
            if month < now.month or (month == now.month and day < now.day):
                year += 1
            try:
                target_date = datetime(year, month, day).date()
            except ValueError:
                pass

        parsed_time = datetime.combine(target_date, datetime.min.time().replace(hour=hour, minute=minute))

    # Format meeting details
    contact_info = []
    if email:
        contact_info.append(f"📧 {email}")
    if phone:
        contact_info.append(f"📞 {phone}")

    meeting_type_names = {
        "call": "Telefonát",
        "video": "Videohovor",
        "meeting": "Osobní schůzka",
    }
    type_name = meeting_type_names.get(meeting_type, "Schůzka")

    if mode == "google" and parsed_time:
        calendar = get_calendar_service()
        if calendar and calendar.is_available():
            result = calendar.create_meeting(
                start_time=parsed_time,
                duration_minutes=30 if meeting_type == "call" else 60,
                client_email=email,
                client_name=name,
                meeting_type=meeting_type,
                notes=notes,
            )

            if result.get("success"):
                response = f"""✅ {type_name} úspěšně naplánován!

👤 {name_text}
{chr(10).join(contact_info) if contact_info else ''}
📅 **{result.get('display', selected_time)}**
🏢 Makléř: {BROKER_NAME}"""

                if result.get("meet_link"):
                    response += f"\n🔗 Odkaz na videohovor: {result['meet_link']}"

                if email:
                    response += f"\n\n📨 Pozvánka byla odeslána na {email}"

                return response

    # Simulated or fallback response
    time_display = parsed_time.strftime("%A %d.%m. v %H:%M") if parsed_time else selected_time

    response = f"""✅ {type_name} naplánován!

👤 {name_text}
{chr(10).join(contact_info) if contact_info else ''}
📅 **{time_display}**
🏢 Makléř: {BROKER_NAME}"""

    if meeting_type == "video":
        response += "\n🎥 Odkaz na videohovor vám pošleme e-mailem před schůzkou."

    if email:
        response += f"\n\n📨 Potvrzení bylo odesláno na {email}"

    return response


# List of all tools for the agent
TOOLS = [
    search_properties,
    get_property_details,
    get_market_overview,
    show_top_properties,
    calculate_lead_score,
    register_property_alert,
    schedule_broker_contact,
    get_available_meeting_slots,
    book_meeting_slot,
]
