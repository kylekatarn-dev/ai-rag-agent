"""
Admin dashboard for monitoring AI agent performance.

Access via: streamlit run app/pages/admin.py
Or add to main app as a page.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
from datetime import datetime

st.set_page_config(
    page_title="Admin Dashboard",
    page_icon="📊",
    layout="wide",
)

st.title("📊 Admin Dashboard")
st.markdown("---")

# Import analytics (after path setup)
try:
    from app.analytics import (
        get_conversation_logger,
        get_property_tracker,
        get_quality_metrics,
    )
    from app.data.loader import load_properties

    analytics_available = True
except ImportError as e:
    st.error(f"Analytics module not available: {e}")
    analytics_available = False

if analytics_available:
    # Tabs for different sections
    tab1, tab2, tab3, tab4 = st.tabs([
        "📈 Metriky",
        "💬 Konverzace",
        "🏠 Nemovitosti",
        "⚠️ Kvalita"
    ])

    with tab1:
        st.header("Přehled metrik")

        metrics = get_quality_metrics()
        stats = metrics.get_dashboard_stats(7)

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric(
                "Konverzace (7 dní)",
                stats["total_conversations"],
            )

        with col2:
            st.metric(
                "Konverzní rate",
                f"{stats['lead_conversion_rate']:.1f}%",
            )

        with col3:
            st.metric(
                "Prům. Lead Score",
                f"{stats['avg_lead_score']:.0f}/100",
            )

        with col4:
            st.metric(
                "Chybovost",
                f"{stats['quality_issue_rate']:.1f}%",
            )

        st.markdown("---")

        # Property tracker stats
        tracker = get_property_tracker()
        tracker_stats = tracker.get_analytics()

        st.subheader("Aktivita nemovitostí")

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("Celkem zobrazení", tracker_stats["total_views"])

        with col2:
            st.metric("Zobrazení (24h)", tracker_stats["views_24h"])

        with col3:
            st.metric("HOT nemovitosti", len(tracker_stats["hot_properties"]))

        if tracker_stats["top_properties"]:
            st.subheader("TOP zobrazované nemovitosti")
            props = load_properties()
            prop_map = {p.id: p for p in props}

            for pid, views in tracker_stats["top_properties"][:5]:
                prop = prop_map.get(pid)
                if prop:
                    st.write(f"- **{prop.location}** ({prop.property_type_cz}): {views} zobrazení")

    with tab2:
        st.header("Historie konverzací")

        conv_logger = get_conversation_logger()
        conversations = conv_logger.list_conversations(20)

        if conversations:
            for conv in conversations:
                with st.expander(
                    f"{conv['started_at'][:10]} - {conv['lead_name'] or 'Neznámý'} "
                    f"(Score: {conv['lead_score']})"
                ):
                    st.write(f"**Session:** {conv['session_id']}")
                    st.write(f"**Lead Score:** {conv['lead_score']}")

                    if conv['quality_flags']:
                        st.warning(f"Problémy: {', '.join(conv['quality_flags'])}")

                    if st.button(f"Zobrazit detail", key=conv['session_id']):
                        # Load full conversation
                        import json
                        with open(conv['filepath'], 'r', encoding='utf-8') as f:
                            full = json.load(f)
                        st.json(full)
        else:
            st.info("Zatím žádné uložené konverzace.")

    with tab3:
        st.header("Přehled nemovitostí")

        props = load_properties()
        tracker = get_property_tracker()

        # Sort by value score
        sorted_props = sorted(props, key=lambda x: x.value_score, reverse=True)

        for prop in sorted_props:
            views = tracker.get_view_count(prop.id)
            trending = "🔥" if tracker.is_hot(prop.id) else ""

            with st.expander(
                f"{trending} {prop.property_type_cz.upper()} - {prop.location} "
                f"| Value: {prop.value_score} | Views: {views}"
            ):
                col1, col2 = st.columns(2)

                with col1:
                    st.write(f"**Plocha:** {prop.area_sqm} m²")
                    st.write(f"**Cena:** {prop.price_czk_sqm} Kč/m²")
                    st.write(f"**Value Score:** {prop.value_score}/100")

                with col2:
                    st.write(f"**Zobrazení (7d):** {views}")
                    st.write(f"**Je HOT:** {'Ano' if prop.is_hot else 'Ne'}")
                    st.write(f"**Je Featured:** {'Ano' if prop.is_featured else 'Ne'}")
                    st.write(f"**Trending:** {'Ano' if tracker.is_hot(prop.id) else 'Ne'}")

    with tab4:
        st.header("Kvalitní report")

        metrics = get_quality_metrics()
        report = metrics.get_quality_report()

        st.markdown(report)

        st.markdown("---")

        st.subheader("Časté problémy")

        stats = metrics.get_dashboard_stats(30)
        if stats["top_issues"]:
            for issue, count in stats["top_issues"]:
                severity = "🔴" if count > 10 else "🟡" if count > 5 else "🟢"
                st.write(f"{severity} **{issue}**: {count}x za posledních 30 dní")
        else:
            st.success("Žádné problémy nezaznamenány!")

    # Sidebar actions
    with st.sidebar:
        st.header("Akce")

        if st.button("🔄 Obnovit data"):
            st.rerun()

        if st.button("🧹 Vyčistit staré záznamy"):
            tracker = get_property_tracker()
            tracker.cleanup_old_data(30)
            metrics = get_quality_metrics()
            metrics.cleanup_old_data(90)
            st.success("Staré záznamy vyčištěny!")

        st.markdown("---")
        st.caption(f"Aktualizováno: {datetime.now().strftime('%H:%M:%S')}")
