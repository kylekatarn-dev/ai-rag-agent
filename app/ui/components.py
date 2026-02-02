"""
UI Components for Streamlit.

Provides reusable components for the chat interface.
"""

import streamlit as st
from typing import Optional

from app.models.property import Property


def render_property_card(prop: Property, show_actions: bool = True) -> None:
    """
    Render a property card with image and details.

    Args:
        prop: Property to display
        show_actions: Whether to show action buttons
    """
    # Card container
    with st.container():
        # Badges
        badges = []
        if prop.is_hot:
            badges.append("HOT")
        if prop.is_featured:
            badges.append("Doporučeno")
        if prop.is_available_now:
            badges.append("Ihned k dispozici")

        badge_html = " ".join([
            f'<span style="background-color: {"#ff4b4b" if b == "HOT" else "#ffa500" if b == "Doporuceno" else "#28a745"}; '
            f'color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px; margin-right: 4px;">{b}</span>'
            for b in badges
        ])

        # Image and details in columns
        col1, col2 = st.columns([1, 2])

        with col1:
            # Property image
            if prop.primary_image_url:
                st.image(
                    prop.primary_image_url,
                    use_container_width=True,
                )
            else:
                # Placeholder
                st.markdown(
                    f"""
                    <div style="
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        height: 150px;
                        border-radius: 8px;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        color: white;
                        font-size: 24px;
                    ">
                        {"" if prop.property_type == "warehouse" else ""}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        with col2:
            # Title and badges
            st.markdown(
                f"""
                <div style="margin-bottom: 8px;">
                    {badge_html}
                </div>
                <h4 style="margin: 0 0 8px 0;">
                    {prop.property_type_cz.upper()} - {prop.location}
                </h4>
                """,
                unsafe_allow_html=True,
            )

            # Details grid
            st.markdown(f"""
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 4px; font-size: 14px;">
                <div><strong>Plocha:</strong> {prop.area_sqm} m²</div>
                <div><strong>Cena:</strong> {prop.price_czk_sqm} Kč/m²</div>
                <div><strong>Celkem:</strong> {prop.total_monthly_rent:,} Kč/měsíc</div>
                <div><strong>Parkování:</strong> {prop.parking_spaces} míst</div>
            </div>
            """, unsafe_allow_html=True)

            # Amenities
            if prop.amenities:
                st.markdown(
                    f"<div style='font-size: 13px; color: #666; margin-top: 4px;'>"
                    f"<strong>Vybavení:</strong> {prop.amenities_cz}</div>",
                    unsafe_allow_html=True,
                )

        # Actions
        if show_actions:
            col1, col2, col3 = st.columns(3)
            with col1:
                map_url = f"https://www.google.com/maps/search/{prop.location.replace(' ', '+')}"
                st.markdown(f"[Zobrazit na mapě]({map_url})")
            with col2:
                if prop.has_virtual_tour:
                    st.markdown(f"[3D prohlídka]({prop.virtual_tour_url})")
            with col3:
                st.button(
                    "Chci prohlídku",
                    key=f"tour_{prop.id}",
                    type="secondary",
                )

        st.markdown("---")


def render_property_list(
    properties: list[Property],
    title: Optional[str] = None,
    max_display: int = 5,
) -> None:
    """
    Render a list of property cards.

    Args:
        properties: List of properties to display
        title: Optional title for the list
        max_display: Maximum properties to show initially
    """
    if not properties:
        st.info("Žádné nemovitosti k zobrazení")
        return

    if title:
        st.subheader(title)

    # Show first N properties
    for prop in properties[:max_display]:
        render_property_card(prop)

    # Show more button
    if len(properties) > max_display:
        remaining = len(properties) - max_display
        if st.button(f"Zobrazit dalších {remaining} nemovitostí"):
            for prop in properties[max_display:]:
                render_property_card(prop)


def render_lead_score_badge(score: int, quality: str) -> str:
    """
    Get HTML for lead score badge.

    Args:
        score: Lead score (0-100)
        quality: Lead quality (hot/warm/cold)

    Returns:
        HTML string for the badge
    """
    colors = {
        "hot": ("#ff4b4b", "HOT"),
        "warm": ("#ffa500", "WARM"),
        "cold": ("#4a90d9", "COLD"),
    }
    color, label = colors.get(quality, colors["cold"])

    return f"""
    <div style="
        background-color: {color};
        color: white;
        padding: 8px 16px;
        border-radius: 8px;
        font-weight: bold;
        display: inline-block;
    ">
        {label} - {score}/100
    </div>
    """


def render_conversation_phase(phase: str) -> str:
    """
    Get display name for conversation phase.

    Args:
        phase: Phase identifier

    Returns:
        Human-readable phase name
    """
    phases = {
        "greeting": "Uvítání",
        "needs_discovery": "Zjišťování požadavků",
        "property_search": "Vyhledávání",
        "recommendation": "Doporučení",
        "objection_handling": "Řešení námitek",
        "contact_capture": "Získávání kontaktu",
        "handoff": "Předání makléři",
    }
    return phases.get(phase, phase)


def render_auth_form() -> tuple[Optional[str], Optional[str]]:
    """
    Render authentication form.

    Returns:
        Tuple of (email, password) if submitted, else (None, None)
    """
    with st.form("auth_form"):
        st.subheader("Přihlášení")
        email = st.text_input("Email")
        password = st.text_input("Heslo", type="password")
        submitted = st.form_submit_button("Přihlásit")

        if submitted:
            return email, password

    return None, None


def render_registration_form() -> tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Render registration form.

    Returns:
        Tuple of (email, password, name) if submitted, else (None, None, None)
    """
    with st.form("register_form"):
        st.subheader("Registrace")
        name = st.text_input("Jméno")
        email = st.text_input("Email")
        password = st.text_input("Heslo", type="password")
        password_confirm = st.text_input("Potvrzení hesla", type="password")
        submitted = st.form_submit_button("Registrovat")

        if submitted:
            if password != password_confirm:
                st.error("Hesla se neshodují")
                return None, None, None
            return email, password, name

    return None, None, None


def render_metrics_dashboard(metrics: dict) -> None:
    """
    Render metrics dashboard.

    Args:
        metrics: Dictionary of metrics to display
    """
    st.subheader("Přehled metrik")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Aktivní relace",
            metrics.get("active_sessions", 0),
        )

    with col2:
        st.metric(
            "Požadavky/min",
            metrics.get("requests_per_minute", 0),
        )

    with col3:
        st.metric(
            "Průměrná odezva",
            f"{metrics.get('avg_response_ms', 0):.0f}ms",
        )

    with col4:
        st.metric(
            "Chybovost",
            f"{metrics.get('error_rate', 0):.1f}%",
        )


def render_property_comparison(properties: list[Property]) -> None:
    """
    Render property comparison table.

    Args:
        properties: Properties to compare
    """
    if len(properties) < 2:
        st.info("Vyberte alespoň 2 nemovitosti pro porovnání")
        return

    st.subheader("Porovnání nemovitostí")

    # Create comparison data
    headers = ["Vlastnost"] + [f"#{p.id}" for p in properties]
    rows = [
        ["Typ"] + [p.property_type_cz for p in properties],
        ["Lokalita"] + [p.location for p in properties],
        ["Plocha (m²)"] + [str(p.area_sqm) for p in properties],
        ["Cena (Kč/m²)"] + [str(p.price_czk_sqm) for p in properties],
        ["Celkem (Kč)"] + [f"{p.total_monthly_rent:,}" for p in properties],
        ["Dostupnost"] + ["Ihned" if p.is_available_now else p.availability for p in properties],
        ["Parkování"] + [str(p.parking_spaces) for p in properties],
    ]

    # Render as table
    st.markdown(
        "<table style='width: 100%; border-collapse: collapse;'>"
        + "".join([
            "<tr>" + "".join([
                f"<{'th' if i == 0 else 'td'} style='border: 1px solid #ddd; padding: 8px; "
                f"{'font-weight: bold;' if j == 0 else ''}'>{cell}</{'th' if i == 0 else 'td'}>"
                for j, cell in enumerate(row)
            ]) + "</tr>"
            for i, row in enumerate([headers] + rows)
        ])
        + "</table>",
        unsafe_allow_html=True,
    )
