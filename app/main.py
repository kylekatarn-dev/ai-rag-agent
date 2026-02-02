import sys
from pathlib import Path

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
from typing import Optional
import uuid

from app.agent import RealEstateAgent
from app.models.lead import LeadQuality
from app.config import (
    SCHEDULING_MODE,
    CALENDLY_URL,
    GOOGLE_CALENDAR_ENABLED,
    RAG_USE_HYBRID_SEARCH,
    RAG_USE_QUERY_EXPANSION,
    RAG_USE_RERANKING,
)
from app.utils import setup_logging, get_logger
from app.ui import (
    render_property_card,
    render_lead_score_badge,
    render_conversation_phase,
    render_metrics_dashboard,
)
from app.analytics.prometheus import get_prometheus_metrics, inc_counter
from app.persistence import LeadRepository

# Initialize logging
setup_logging()
logger = get_logger(__name__)


# Page config
st.set_page_config(
    page_title="Realitní AI Asistent",
    page_icon="🏢",
    layout="wide",
)

# Custom CSS
st.markdown("""
<style>
    .stChatMessage {
        padding: 1rem;
    }
    /* Uniform property images in chat */
    .stChatMessage img {
        width: 100%;
        max-width: 400px;
        height: 200px;
        object-fit: cover;
        border-radius: 8px;
        margin-bottom: 0.5rem;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .lead-score-hot {
        background-color: #ff4b4b;
        color: white;
        padding: 0.5rem 1rem;
        border-radius: 0.5rem;
        font-weight: bold;
    }
    .lead-score-warm {
        background-color: #ffa500;
        color: white;
        padding: 0.5rem 1rem;
        border-radius: 0.5rem;
        font-weight: bold;
    }
    .lead-score-cold {
        background-color: #4a90d9;
        color: white;
        padding: 0.5rem 1rem;
        border-radius: 0.5rem;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)


def init_session_state():
    """Initialize session state variables."""
    # Generate or restore session ID
    if "session_id" not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())

    # Admin mode (for metrics access - simple password protection)
    if "is_admin" not in st.session_state:
        st.session_state.is_admin = False

    # Initialize lead repository for persistence
    if "lead_repo" not in st.session_state:
        st.session_state.lead_repo = LeadRepository()

    # Initialize agent with session ID
    if "agent" not in st.session_state:
        use_rag_memory = st.session_state.get("rag_memory", False)
        st.session_state.agent = RealEstateAgent(
            session_id=st.session_state.session_id,
            use_rag_memory=use_rag_memory,
        )

    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "summary_generated" not in st.session_state:
        st.session_state.summary_generated = False
    if "scheduling_mode" not in st.session_state:
        st.session_state.scheduling_mode = SCHEDULING_MODE
    if "show_metrics" not in st.session_state:
        st.session_state.show_metrics = False

    # RAG settings
    if "rag_hybrid" not in st.session_state:
        st.session_state.rag_hybrid = RAG_USE_HYBRID_SEARCH
    if "rag_expansion" not in st.session_state:
        st.session_state.rag_expansion = RAG_USE_QUERY_EXPANSION
    if "rag_reranking" not in st.session_state:
        st.session_state.rag_reranking = RAG_USE_RERANKING
    if "rag_memory" not in st.session_state:
        st.session_state.rag_memory = False  # RAG memory optional, off by default

    # Track metrics
    inc_counter("requests_total", labels={"type": "page_load"})


def display_sidebar():
    """Display sidebar with lead info and controls."""
    with st.sidebar:
        st.header("🏢 PROCHAZKA REALITY")
        st.caption("AI Asistent pro komerční nemovitosti")
        st.markdown("---")

        # Lead Score
        lead = st.session_state.agent.get_lead()
        score = lead.lead_score
        quality = lead.lead_quality

        st.subheader("Lead Score")

        if quality == LeadQuality.HOT:
            st.markdown(f'<div class="lead-score-hot">🔥 {score}/100 - HOT</div>', unsafe_allow_html=True)
        elif quality == LeadQuality.WARM:
            st.markdown(f'<div class="lead-score-warm">🌡️ {score}/100 - WARM</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="lead-score-cold">❄️ {score}/100 - COLD</div>', unsafe_allow_html=True)

        st.markdown("---")

        # Lead Requirements
        st.subheader("Požadavky klienta")

        prop_type = {
            "warehouse": "🏭 Sklad",
            "office": "🏢 Kancelář",
        }.get(lead.property_type, "❓ Neurčeno")
        st.write(f"**Typ:** {prop_type}")

        if lead.min_area_sqm or lead.max_area_sqm:
            area = f"{lead.min_area_sqm or '?'} - {lead.max_area_sqm or '?'} m²"
        else:
            area = "Neurčeno"
        st.write(f"**Plocha:** {area}")

        if lead.preferred_locations:
            st.write(f"**Lokalita:** {', '.join(lead.preferred_locations)}")
        else:
            st.write("**Lokalita:** Neurčeno")

        if lead.max_price_czk_sqm:
            st.write(f"**Rozpočet:** max {lead.max_price_czk_sqm} Kč/m²")
        else:
            st.write("**Rozpočet:** Neurčeno")

        urgency_map = {
            "immediate": "Ihned",
            "1-3months": "1-3 měsíce",
            "3-6months": "3-6 měsíců",
            "flexible": "Flexibilní",
        }
        urgency = urgency_map.get(lead.move_in_urgency, "Neurčeno")
        st.write(f"**Nástup:** {urgency}")

        st.markdown("---")

        # Contact Info
        st.subheader("Kontakt")
        st.write(f"**Jméno:** {lead.name or 'Nezjištěno'}")
        st.write(f"**Email:** {lead.email or 'Nezjištěno'}")
        st.write(f"**Telefon:** {lead.phone or 'Nezjištěno'}")
        st.write(f"**Firma:** {lead.company or 'Nezjištěno'}")

        # Contact preferences
        if lead.preferred_contact_method:
            method_map = {"email": "📧 E-mail", "phone": "📞 Telefon", "sms": "💬 SMS"}
            st.write(f"**Preferuje:** {method_map.get(lead.preferred_contact_method, lead.preferred_contact_method)}")

        if lead.preferred_call_time:
            st.write(f"**Čas kontaktu:** {lead.preferred_call_time}")

        # Notification & broker interest
        if lead.wants_notifications or lead.wants_broker_contact:
            st.markdown("---")
            st.subheader("Zájem")
            if lead.wants_notifications:
                st.write("✅ Chce notifikace o nových nabídkách")
            if lead.wants_broker_contact:
                st.write("✅ Chce spojit s makléřem")

        st.markdown("---")

        # Actions
        col1, col2 = st.columns(2)

        with col1:
            if st.button("🔄 Nová konverzace", use_container_width=True):
                st.session_state.agent.reset()
                st.session_state.messages = []
                st.session_state.summary_generated = False
                st.rerun()

        with col2:
            if st.button("📋 Souhrn", use_container_width=True):
                st.session_state.summary_generated = True
                st.rerun()

        st.markdown("---")

        # Scheduling Mode Toggle
        st.subheader("⚙️ Nastavení")

        scheduling_options = {
            "simulated": "Simulované (demo)",
            "calendly": "Calendly",
            "google": "Google Calendar",
        }

        current_mode = st.session_state.scheduling_mode
        mode_index = {"simulated": 0, "calendly": 1, "google": 2}.get(current_mode, 0)

        selected_mode = st.radio(
            "Rezervace schůzek:",
            options=list(scheduling_options.keys()),
            format_func=lambda x: scheduling_options[x],
            index=mode_index,
            key="scheduling_mode_radio",
        )

        if selected_mode != current_mode:
            st.session_state.scheduling_mode = selected_mode
            st.rerun()

        # Show mode-specific info
        if st.session_state.scheduling_mode == "calendly":
            st.caption(f"🔗 {CALENDLY_URL}")
            if "your-username" in CALENDLY_URL:
                st.warning("⚠️ Nastavte CALENDLY_URL v .env")

        elif st.session_state.scheduling_mode == "google":
            if GOOGLE_CALENDAR_ENABLED:
                st.caption("✅ Google Calendar připojen")
            else:
                st.warning("⚠️ Nastavte GOOGLE_CALENDAR_ENABLED=true v .env")
                st.caption("Zobrazují se simulované termíny")

        st.markdown("---")

        # RAG Settings
        st.subheader("🔍 Vyhledávání (RAG)")

        st.session_state.rag_hybrid = st.checkbox(
            "Hybridní vyhledávání",
            value=st.session_state.rag_hybrid,
            help="Kombinuje vektorové vyhledávání s klíčovými slovy (BM25)",
        )

        st.session_state.rag_expansion = st.checkbox(
            "Rozšíření dotazu",
            value=st.session_state.rag_expansion,
            help="Automaticky rozšiřuje dotaz o synonyma a související lokality",
        )

        st.session_state.rag_reranking = st.checkbox(
            "LLM Re-ranking",
            value=st.session_state.rag_reranking,
            help="Používá LLM k přeřazení výsledků podle relevance (pomalejší, přesnější)",
        )

        st.session_state.rag_memory = st.checkbox(
            "Chat Memory (RAG)",
            value=st.session_state.rag_memory,
            help="Ukládá historii konverzace do vektorové DB pro efektivní vyhledávání kontextu",
        )

        # Show RAG mode summary
        rag_features = []
        if st.session_state.rag_hybrid:
            rag_features.append("Hybrid")
        if st.session_state.rag_expansion:
            rag_features.append("Expansion")
        if st.session_state.rag_reranking:
            rag_features.append("Rerank")
        if st.session_state.rag_memory:
            rag_features.append("Memory")

        if rag_features:
            st.caption(f"Aktivní: {' + '.join(rag_features)}")
        else:
            st.caption("Základní vektorové vyhledávání")

        st.markdown("---")

        # Conversation phase indicator
        st.subheader("💬 Fáze konverzace")
        phase = st.session_state.agent.state.current_phase
        phase_display = render_conversation_phase(phase)
        st.info(f"📍 {phase_display}")

        # Context stats
        memory_stats = st.session_state.agent.get_memory_stats()
        if memory_stats:
            with st.expander("🧠 Kontext"):
                st.caption(f"Zpráv: {memory_stats['total_messages']}")
                if memory_stats['has_summary']:
                    st.caption(f"Souhrn: {memory_stats['summary_length']} znaků")
                    st.caption(f"Sumarizováno od: zprávy {memory_stats['last_summarized_at']}")
                if memory_stats.get('rag_memory'):
                    st.caption("RAG Memory: aktivní")
                    st.caption(f"  Uloženo: {memory_stats['rag_memory'].get('stored_turns', 0)}")

        st.markdown("---")

        # Metrics toggle (admin feature - could add password protection)
        with st.expander("🔧 Admin"):
            if st.button("📊 Metriky", use_container_width=True):
                st.session_state.show_metrics = not st.session_state.show_metrics
                st.rerun()


def display_chat():
    """Display chat interface."""
    st.header("💬 Chat s asistentem")

    # Display existing messages
    for i, message in enumerate(st.session_state.messages):
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

            # Show property cards for assistant messages that have properties
            if message["role"] == "assistant" and message.get("properties"):
                st.markdown("---")
                for prop in message["properties"][:5]:  # Limit to 5 cards
                    render_property_card(prop)

    # Initial greeting if no messages
    if not st.session_state.messages:
        greeting = """Dobrý den! 👋

Jsem PETRA, AI asistentka realitní kanceláře PROCHAZKA REALITY. Pomohu vám najít ideální komerční prostory - sklady nebo kanceláře po celé ČR.

**Co pro vás mohu udělat:**
- Ukázat vám dostupné nemovitosti podle vašich požadavků
- Poradit s výběrem vhodné lokality a velikosti
- Připravit podklady pro prohlídku

Řekněte mi, co hledáte - třeba "sklad v Praze" nebo "kancelář pro 10 lidí" - a hned vám ukážu možnosti!"""

        st.session_state.messages.append({"role": "assistant", "content": greeting})
        with st.chat_message("assistant"):
            st.markdown(greeting)

    # Chat input
    if prompt := st.chat_input("Napište zprávu..."):
        # Track request
        inc_counter("requests_total", labels={"type": "chat_message"})

        # Add user message
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Generate response
        with st.chat_message("assistant"):
            response_placeholder = st.empty()
            full_response = ""

            for chunk in st.session_state.agent.chat(prompt):
                full_response += chunk
                response_placeholder.markdown(full_response + "▌")

            response_placeholder.markdown(full_response)

            # Check if properties were shown and display cards
            shown_properties = st.session_state.agent.state.last_shown_properties
            if shown_properties:
                st.markdown("---")
                for prop in shown_properties[:5]:  # Limit to 5 cards
                    render_property_card(prop)

        # Store message with properties for future display
        message_data = {"role": "assistant", "content": full_response}
        if shown_properties:
            message_data["properties"] = shown_properties
            # Clear last shown after storing
            st.session_state.agent.state.last_shown_properties = []

        # Persist lead data to database
        try:
            lead = st.session_state.agent.get_lead()
            st.session_state.lead_repo.save(lead, session_id=st.session_state.session_id)
            inc_counter("leads_created_total")
        except Exception as e:
            logger.warning(f"Failed to persist lead: {e}")

        st.session_state.messages.append(message_data)
        st.rerun()  # Refresh to update sidebar


def display_summary():
    """Display broker summary modal."""
    st.header("📋 Souhrn pro makléře")

    summary = st.session_state.agent.generate_summary()
    st.markdown(summary)

    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("⬅️ Zpět na chat"):
            st.session_state.summary_generated = False
            st.rerun()

    with col2:
        st.download_button(
            label="📥 Stáhnout souhrn",
            data=summary,
            file_name="lead_summary.md",
            mime="text/markdown",
        )


def display_metrics():
    """Display Prometheus metrics dashboard."""
    st.header("📊 Metriky aplikace")

    metrics = get_prometheus_metrics()
    summary = metrics.get_summary()

    render_metrics_dashboard({
        "active_sessions": summary["gauges"].get("active_sessions", 0),
        "requests_per_minute": summary["counters"].get("requests_total", 0),
        "avg_response_ms": summary["histograms"].get("request_duration_seconds", {}).get("avg", 0) * 1000,
        "error_rate": (
            summary["counters"].get("requests_errors_total", 0) /
            max(summary["counters"].get("requests_total", 1), 1)
        ) * 100,
    })

    st.markdown("---")

    # Detailed metrics
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("LLM Metriky")
        st.metric("Celkem volání", summary["counters"].get("llm_calls_total", 0))
        st.metric("Celkem tokenů", summary["counters"].get("llm_tokens_total", 0))
        st.metric("Chyby LLM", summary["counters"].get("llm_errors_total", 0))

        llm_hist = summary["histograms"].get("llm_response_time_seconds", {})
        if llm_hist.get("count", 0) > 0:
            st.metric("Průměrná odezva LLM", f"{llm_hist.get('avg', 0):.2f}s")
            st.metric("P95 odezva LLM", f"{llm_hist.get('p95', 0):.2f}s")

    with col2:
        st.subheader("Lead Metriky")
        st.metric("Vytvořeno leadů", summary["counters"].get("leads_created_total", 0))
        st.metric("Kvalifikovaných", summary["counters"].get("leads_qualified_total", 0))
        st.metric("Konvertovaných", summary["counters"].get("leads_converted_total", 0))

        st.subheader("Cache")
        st.metric("Cache hits", summary["counters"].get("cache_hits_total", 0))
        st.metric("Cache misses", summary["counters"].get("cache_misses_total", 0))

    st.markdown("---")

    # Raw Prometheus format
    with st.expander("📄 Prometheus formát"):
        st.code(metrics.export_metrics(), language="text")

    if st.button("⬅️ Zpět na chat"):
        st.session_state.show_metrics = False
        st.rerun()


def main():
    """Main application entry point."""
    logger.info("Starting Realitni AI Asistent")
    init_session_state()
    display_sidebar()

    # Show different views based on state
    if st.session_state.show_metrics:
        display_metrics()
    elif st.session_state.summary_generated:
        display_summary()
    else:
        display_chat()


if __name__ == "__main__":
    main()
