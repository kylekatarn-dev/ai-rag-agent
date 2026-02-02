from datetime import datetime

from app.models.lead import Lead, LeadQuality
from app.models.property import Property
from app.models.broker import Broker, DEFAULT_BROKERS
from app.data.loader import get_property_by_id


def generate_broker_summary(
    lead: Lead,
    matched_properties: list[Property] | None = None,
    conversation_log: str = "",
) -> str:
    """Generate a structured summary for the broker."""

    # Get matched properties if not provided
    if matched_properties is None and lead.matched_properties:
        matched_properties = [
            get_property_by_id(pid) for pid in lead.matched_properties
        ]
        matched_properties = [p for p in matched_properties if p is not None]

    # Find best broker for this lead
    assigned_broker = _find_best_broker(lead)

    # Build summary
    quality_emoji = lead.get_quality_emoji()
    quality_label = {
        LeadQuality.HOT: "HOT",
        LeadQuality.WARM: "WARM",
        LeadQuality.COLD: "COLD",
    }[lead.lead_quality]

    # Format requirements
    requirements = _format_requirements(lead)

    # Format matched properties
    properties_section = _format_properties(matched_properties, lead.best_match_id)

    # Format follow-up actions
    follow_up = _generate_follow_up_actions(lead)

    summary = f"""# Souhrn leadu pro makléře

## Základní info
- **Jméno:** {lead.name or 'Neuvedeno'}
- **Firma:** {lead.company or 'Neuvedeno'}
- **Email:** {lead.email or 'Neuvedeno'}
- **Telefon:** {lead.phone or 'Neuvedeno'}
- **Datum:** {datetime.now().strftime('%Y-%m-%d %H:%M')}

## Lead Score: {lead.lead_score}/100 ({quality_label} {quality_emoji})

## Požadavky klienta
{requirements}

## Doporučené nemovitosti
{properties_section}

## Shrnutí konverzace
{lead.conversation_summary or conversation_log or 'Konverzace nebyla zaznamenána.'}

## Doporučené další kroky
{follow_up}

## Přiřazený makléř
- **Jméno:** {assigned_broker.name}
- **Email:** {assigned_broker.email}
- **Telefon:** {assigned_broker.phone}

---
*Vygenerováno AI asistentem*
"""
    return summary


def _format_requirements(lead: Lead) -> str:
    """Format lead requirements as bullet points."""
    lines = []

    prop_type = {
        "warehouse": "Sklad",
        "office": "Kancelář",
    }.get(lead.property_type, "Neurčeno")
    lines.append(f"- **Typ:** {prop_type}")

    if lead.min_area_sqm and lead.max_area_sqm:
        lines.append(f"- **Plocha:** {lead.min_area_sqm}-{lead.max_area_sqm} m²")
    elif lead.min_area_sqm:
        lines.append(f"- **Plocha:** min. {lead.min_area_sqm} m²")
    elif lead.max_area_sqm:
        lines.append(f"- **Plocha:** max. {lead.max_area_sqm} m²")
    else:
        lines.append("- **Plocha:** Neurčeno")

    if lead.preferred_locations:
        lines.append(f"- **Lokalita:** {', '.join(lead.preferred_locations)}")
    else:
        lines.append("- **Lokalita:** Neurčeno")

    if lead.max_price_czk_sqm:
        lines.append(f"- **Rozpočet:** max {lead.max_price_czk_sqm} Kč/m²/měsíc")
    else:
        lines.append("- **Rozpočet:** Neurčeno")

    if lead.move_in_date:
        lines.append(f"- **Nástup:** {lead.move_in_date.strftime('%Y-%m-%d')}")
    elif lead.move_in_urgency:
        urgency_map = {
            "immediate": "Ihned",
            "1-3months": "1-3 měsíce",
            "3-6months": "3-6 měsíců",
            "flexible": "Flexibilní",
        }
        lines.append(f"- **Nástup:** {urgency_map.get(lead.move_in_urgency, lead.move_in_urgency)}")
    else:
        lines.append("- **Nástup:** Neurčeno")

    if lead.required_amenities:
        lines.append(f"- **Požadované vybavení:** {', '.join(lead.required_amenities)}")

    if lead.parking_needed > 0:
        lines.append(f"- **Parkování:** {lead.parking_needed} míst")

    return "\n".join(lines)


def _format_properties(
    properties: list[Property] | None,
    best_match_id: int | None = None
) -> str:
    """Format matched properties for the summary."""
    if not properties:
        return "Žádné nemovitosti nebyly nalezeny."

    lines = []
    for i, prop in enumerate(properties[:5], 1):
        is_best = prop.id == best_match_id
        best_marker = " ⭐ Nejlepší shoda" if is_best else ""
        hot_marker = " 🔥" if prop.is_hot else ""

        lines.append(f"""
### {i}. ID {prop.id} - {prop.location}{best_marker}{hot_marker}
- Typ: {prop.property_type_cz}
- Plocha: {prop.area_sqm} m²
- Cena: {prop.price_czk_sqm} Kč/m²/měsíc
- Celkem: {prop.total_monthly_rent:,} Kč/měsíc
- Dostupnost: {'ihned' if prop.is_available_now else prop.availability}
- Vybavení: {prop.amenities_cz or 'základní'}
""")

    return "\n".join(lines)


def _generate_follow_up_actions(lead: Lead) -> str:
    """Generate recommended follow-up actions based on lead quality."""
    actions = []

    if lead.lead_quality == LeadQuality.HOT:
        actions = [
            "1. [ ] **PRIORITY:** Zavolat do 2 hodin",
            "2. [ ] Nabídnout prohlídku nejlepší nemovitosti",
            "3. [ ] Připravit cenovou kalkulaci",
            "4. [ ] Poslat personalizovanou nabídku emailem",
        ]
    elif lead.lead_quality == LeadQuality.WARM:
        actions = [
            "1. [ ] Zavolat do 24 hodin",
            "2. [ ] Poslat email s doporučenými nemovitostmi",
            "3. [ ] Nabídnout termín prohlídky",
            "4. [ ] Zjistit detailnější požadavky",
        ]
    else:  # COLD
        actions = [
            "1. [ ] Poslat informační email",
            "2. [ ] Přidat do nurture kampaně",
            "3. [ ] Naplánovat follow-up za 2 týdny",
            "4. [ ] Nabídnout newsletter s novými nabídkami",
        ]

    # Add specific actions based on lead data
    if not lead.has_contact_info:
        actions.insert(0, "0. [ ] ⚠️ **CHYBÍ KONTAKT** - Získat email nebo telefon")

    if lead.key_objections:
        actions.append(f"- **Námitky k řešení:** {', '.join(lead.key_objections)}")

    return "\n".join(actions)


def _find_best_broker(lead: Lead) -> Broker:
    """Find the best broker for this lead."""
    best_broker = DEFAULT_BROKERS[0]  # Default
    best_score = 0

    for broker in DEFAULT_BROKERS:
        if not broker.can_accept_leads:
            continue

        score = 0

        # Check property type match
        if lead.property_type and broker.matches_property_type(lead.property_type):
            score += 10

        # Check region match
        if lead.preferred_locations:
            for loc in lead.preferred_locations:
                if broker.matches_region(loc):
                    score += 10
                    break

        # Prefer less loaded brokers
        score += (broker.max_leads - broker.current_leads_count)

        if score > best_score:
            best_score = score
            best_broker = broker

    return best_broker
