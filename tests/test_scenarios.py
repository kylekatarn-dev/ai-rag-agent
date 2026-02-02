"""
Test scenarios for the Real Estate AI Assistant.

These tests simulate the three required scenarios:
1. Realistic, quality lead
2. Vague inquiry
3. Unrealistic requirements
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.agent import RealEstateAgent
from app.models.lead import LeadQuality


def run_scenario(agent: RealEstateAgent, messages: list[str], scenario_name: str) -> dict:
    """Run a test scenario and collect results."""
    print(f"\n{'='*60}")
    print(f"SCÉNÁŘ: {scenario_name}")
    print('='*60)

    agent.reset()
    conversation_log = []

    for message in messages:
        print(f"\n👤 Klient: {message}")
        conversation_log.append(f"Klient: {message}")

        response = ""
        for chunk in agent.chat(message):
            response += chunk

        print(f"\n🤖 Asistent: {response}")
        conversation_log.append(f"Asistent: {response}")

    # Get final lead data
    lead = agent.get_lead()
    summary = agent.generate_summary()

    print(f"\n{'-'*40}")
    print("VÝSLEDKY:")
    print(f"Lead Score: {lead.lead_score}/100")
    print(f"Lead Quality: {lead.lead_quality.value}")
    print(f"Customer Type: {lead.customer_type.value if lead.customer_type else 'N/A'}")
    print(f"Matched Properties: {lead.matched_properties}")
    print(f"{'-'*40}")

    return {
        "scenario": scenario_name,
        "lead_score": lead.lead_score,
        "lead_quality": lead.lead_quality,
        "customer_type": lead.customer_type,
        "matched_properties": lead.matched_properties,
        "conversation": conversation_log,
        "summary": summary,
    }


def test_scenario_1_realistic():
    """Scenario 1: Realistic and quality lead."""
    agent = RealEstateAgent()

    messages = [
        "Dobrý den, hledám sklad v okolí Prahy.",
        "Potřebuji přibližně 600-800 m², ideálně s nakládací rampou.",
        "Rozpočet mám do 100 Kč za metr čtvereční měsíčně.",
        "Potřeboval bych to od března, nejpozději do konce dubna.",
        "Jsem Jan Novák z firmy ABC Logistics, můžete mě kontaktovat na jan.novak@abc.cz nebo 777 123 456.",
    ]

    return run_scenario(agent, messages, "1. Realistický a kvalitní lead")


def test_scenario_2_vague():
    """Scenario 2: Vague inquiry."""
    agent = RealEstateAgent()

    messages = [
        "Dobrý den, potřeboval bych nějaký prostor pro firmu.",
        "No, nevím přesně... asi bych potřeboval nějakou kancelář nebo sklad.",
        "Kancelář by byla lepší, ale ještě přemýšlím.",
        "Někde v Praze by to chtělo, ale nevím kde přesně.",
        "Rozpočet? To musím ještě probrat s vedením...",
    ]

    return run_scenario(agent, messages, "2. Vágní dotaz")


def test_scenario_3_unrealistic():
    """Scenario 3: Unrealistic requirements."""
    agent = RealEstateAgent()

    messages = [
        "Hledám reprezentativní kancelář přímo v centru Prahy.",
        "Potřebuji minimálně 500 m² s vlastním parkováním.",
        "Můj maximální rozpočet je 80 Kč za metr čtvereční.",
        "A potřebuji to ihned, nejpozději do konce měsíce.",
        "To je ale hodně... nemáte nic levnějšího? Třeba za 50 Kč?",
    ]

    return run_scenario(agent, messages, "3. Nereálný požadavek")


def main():
    """Run all test scenarios."""
    print("="*60)
    print("TESTOVACÍ SCÉNÁŘE - Realitní AI Asistent")
    print("="*60)

    results = []

    # Run scenarios
    results.append(test_scenario_1_realistic())
    results.append(test_scenario_2_vague())
    results.append(test_scenario_3_unrealistic())

    # Summary
    print("\n" + "="*60)
    print("SHRNUTÍ VŠECH SCÉNÁŘŮ")
    print("="*60)

    for r in results:
        emoji = {
            LeadQuality.HOT: "🔥",
            LeadQuality.WARM: "🌡️",
            LeadQuality.COLD: "❄️",
        }.get(r["lead_quality"], "❓")

        print(f"\n{r['scenario']}")
        print(f"  Score: {r['lead_score']}/100 {emoji} {r['lead_quality'].value.upper()}")
        print(f"  Type: {r['customer_type'].value if r['customer_type'] else 'N/A'}")
        print(f"  Matches: {len(r['matched_properties'])} properties")

    # Save results to files
    docs_dir = Path(__file__).parent.parent / "docs"
    docs_dir.mkdir(exist_ok=True)

    for i, r in enumerate(results, 1):
        filename = docs_dir / f"test_scenario_{i}.md"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(f"# {r['scenario']}\n\n")
            f.write("## Konverzace\n\n")
            for line in r["conversation"]:
                if line.startswith("Klient:"):
                    f.write(f"**{line}**\n\n")
                else:
                    f.write(f"{line}\n\n")
            f.write("---\n\n")
            f.write(r["summary"])

        print(f"\nSaved: {filename}")

    print("\n✅ Všechny testy dokončeny!")


if __name__ == "__main__":
    main()
