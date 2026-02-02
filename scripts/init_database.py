"""
Database Initialization Script.

Initializes the SQLite database with all properties.
Run this once to set up the database.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.persistence.database import get_database
from app.persistence.repositories import PropertyRepository
from app.models.property import Property


# All 20 properties with proper regions
PROPERTIES = [
    {
        "id": 1,
        "property_type": "warehouse",
        "location": "Praha-východ",
        "region": "Čechy",
        "country": "CZ",
        "area_sqm": 650,
        "price_czk_sqm": 110,
        "availability": "ihned",
        "parking_spaces": 0,
        "amenities": ["rampa", "vytapeni"],
        "is_featured": True,
        "is_hot": False,
        "priority_score": 85,
        "commission_rate": 2.5,
        "thumbnail_url": "https://placehold.co/400x250/2C3E50/FFFFFF?text=Sklad+650m²",
        "highway_access": "D11 (3 km)",
        "transport_notes": "Průmyslová zóna, dobrá dostupnost z Prahy"
    },
    {
        "id": 2,
        "property_type": "warehouse",
        "location": "Říčany u Prahy",
        "region": "Čechy",
        "country": "CZ",
        "area_sqm": 720,
        "price_czk_sqm": 95,
        "availability": "2026-02-01",
        "parking_spaces": 0,
        "amenities": ["bez_rampy", "vyska_6m"],
        "is_featured": False,
        "is_hot": False,
        "priority_score": 70,
        "commission_rate": 2.0,
        "thumbnail_url": "https://placehold.co/400x250/34495E/FFFFFF?text=Sklad+720m²",
        "highway_access": "D1 (4 km)",
        "transport_notes": "Blízko Pražského okruhu"
    },
    {
        "id": 3,
        "property_type": "warehouse",
        "location": "Brno-jih",
        "region": "Morava",
        "country": "CZ",
        "area_sqm": 1200,
        "price_czk_sqm": 85,
        "availability": "2026-03-01",
        "parking_spaces": 0,
        "amenities": ["rampa", "vysoke_stropy_10m"],
        "is_featured": True,
        "is_hot": True,
        "priority_score": 95,
        "commission_rate": 3.0,
        "thumbnail_url": "https://placehold.co/400x250/E74C3C/FFFFFF?text=🔥+Sklad+1200m²",
        "highway_access": "D1, D2 (2 km)",
        "transport_notes": "Logistický park CTPark, 24/7 přístup pro kamiony"
    },
    {
        "id": 4,
        "property_type": "warehouse",
        "location": "Hostivice",
        "region": "Čechy",
        "country": "CZ",
        "area_sqm": 400,
        "price_czk_sqm": 105,
        "availability": "ihned",
        "parking_spaces": 0,
        "amenities": ["prizemni"],
        "is_featured": False,
        "is_hot": False,
        "priority_score": 60,
        "commission_rate": 2.0,
        "thumbnail_url": "https://placehold.co/400x250/7F8C8D/FFFFFF?text=Sklad+400m²",
        "highway_access": "D6 (5 km)",
        "transport_notes": "Blízko letiště Václava Havla"
    },
    {
        "id": 5,
        "property_type": "warehouse",
        "location": "Ostrava-Hrabová",
        "region": "Morava",
        "country": "CZ",
        "area_sqm": 2000,
        "price_czk_sqm": 75,
        "availability": "2026-04-01",
        "parking_spaces": 0,
        "amenities": ["rampa", "kancelare_v_cene_50m2"],
        "is_featured": True,
        "is_hot": True,
        "priority_score": 90,
        "commission_rate": 3.5,
        "thumbnail_url": "https://placehold.co/400x250/E74C3C/FFFFFF?text=🔥+Sklad+2000m²",
        "highway_access": "D1 (1 km)",
        "transport_notes": "Průmyslová zóna Hrabová, železniční vlečka v areálu"
    },
    {
        "id": 6,
        "property_type": "warehouse",
        "location": "Plzeň-východ",
        "region": "Čechy",
        "country": "CZ",
        "area_sqm": 550,
        "price_czk_sqm": 90,
        "availability": "ihned",
        "parking_spaces": 0,
        "amenities": ["vytapeni"],
        "is_featured": False,
        "is_hot": False,
        "priority_score": 65,
        "commission_rate": 2.0,
        "thumbnail_url": "https://placehold.co/400x250/95A5A6/FFFFFF?text=Sklad+550m²",
        "highway_access": "D5 (3 km)",
        "transport_notes": "Strategická poloha mezi Prahou a Německem"
    },
    {
        "id": 7,
        "property_type": "warehouse",
        "location": "Olomouc",
        "region": "Morava",
        "country": "CZ",
        "area_sqm": 800,
        "price_czk_sqm": 80,
        "availability": "2026-02-01",
        "parking_spaces": 0,
        "amenities": ["rampa"],
        "is_featured": False,
        "is_hot": False,
        "priority_score": 70,
        "commission_rate": 2.0,
        "thumbnail_url": "https://placehold.co/400x250/34495E/FFFFFF?text=Sklad+800m²",
        "highway_access": "D35 (4 km)",
        "transport_notes": "Napojení na Brno i Ostravu"
    },
    {
        "id": 8,
        "property_type": "warehouse",
        "location": "Průhonice (Praha-jih)",
        "region": "Čechy",
        "country": "CZ",
        "area_sqm": 450,
        "price_czk_sqm": 125,
        "availability": "ihned",
        "parking_spaces": 0,
        "amenities": ["klimatizovany", "moderni"],
        "is_featured": True,
        "is_hot": False,
        "priority_score": 80,
        "commission_rate": 2.5,
        "thumbnail_url": "https://placehold.co/400x250/3498DB/FFFFFF?text=⭐+Sklad+450m²",
        "highway_access": "D1 (1 km)",
        "transport_notes": "Prémiová lokalita u D1, moderní vybavení"
    },
    {
        "id": 9,
        "property_type": "office",
        "location": "Praha 4 – Pankrác",
        "region": "Čechy",
        "country": "CZ",
        "area_sqm": 120,
        "price_czk_sqm": 320,
        "availability": "ihned",
        "parking_spaces": 2,
        "amenities": ["klimatizace", "meeting_room"],
        "is_featured": True,
        "is_hot": False,
        "priority_score": 85,
        "commission_rate": 2.5,
        "thumbnail_url": "https://placehold.co/400x250/3498DB/FFFFFF?text=⭐+Kancelář+120m²"
    },
    {
        "id": 10,
        "property_type": "office",
        "location": "Praha 5 – Smíchov",
        "region": "Čechy",
        "country": "CZ",
        "area_sqm": 85,
        "price_czk_sqm": 290,
        "availability": "2026-02-01",
        "parking_spaces": 0,
        "amenities": ["open_space", "bez_parkovani"],
        "is_featured": False,
        "is_hot": False,
        "priority_score": 65,
        "commission_rate": 2.0,
        "thumbnail_url": "https://placehold.co/400x250/1ABC9C/FFFFFF?text=Kancelář+85m²"
    },
    {
        "id": 11,
        "property_type": "office",
        "location": "Praha 1 – Nové Město",
        "region": "Čechy",
        "country": "CZ",
        "area_sqm": 200,
        "price_czk_sqm": 450,
        "availability": "ihned",
        "parking_spaces": 4,
        "amenities": ["reprezentativni", "recepce"],
        "is_featured": True,
        "is_hot": True,
        "priority_score": 95,
        "commission_rate": 3.5,
        "thumbnail_url": "https://placehold.co/400x250/E74C3C/FFFFFF?text=🔥+Kancelář+200m²"
    },
    {
        "id": 12,
        "property_type": "office",
        "location": "Brno – centrum",
        "region": "Morava",
        "country": "CZ",
        "area_sqm": 150,
        "price_czk_sqm": 220,
        "availability": "2026-03-01",
        "parking_spaces": 2,
        "amenities": ["klimatizace"],
        "is_featured": False,
        "is_hot": False,
        "priority_score": 70,
        "commission_rate": 2.0,
        "thumbnail_url": "https://placehold.co/400x250/16A085/FFFFFF?text=Kancelář+150m²"
    },
    {
        "id": 13,
        "property_type": "office",
        "location": "Praha 8 – Karlín",
        "region": "Čechy",
        "country": "CZ",
        "area_sqm": 300,
        "price_czk_sqm": 350,
        "availability": "ihned",
        "parking_spaces": 6,
        "amenities": ["moderni_budova", "terasa"],
        "is_featured": True,
        "is_hot": True,
        "priority_score": 92,
        "commission_rate": 3.0,
        "thumbnail_url": "https://placehold.co/400x250/E74C3C/FFFFFF?text=🔥+Kancelář+300m²"
    },
    {
        "id": 14,
        "property_type": "office",
        "location": "Ostrava – centrum",
        "region": "Morava",
        "country": "CZ",
        "area_sqm": 100,
        "price_czk_sqm": 150,
        "availability": "ihned",
        "parking_spaces": 1,
        "amenities": ["zakladni_standard"],
        "is_featured": False,
        "is_hot": False,
        "priority_score": 55,
        "commission_rate": 1.5,
        "thumbnail_url": "https://placehold.co/400x250/95A5A6/FFFFFF?text=Kancelář+100m²"
    },
    {
        "id": 15,
        "property_type": "office",
        "location": "Praha 2 – Vinohrady",
        "region": "Čechy",
        "country": "CZ",
        "area_sqm": 60,
        "price_czk_sqm": 380,
        "availability": "2026-01-15",
        "parking_spaces": 0,
        "amenities": ["po_rekonstrukci", "bez_parkovani"],
        "is_featured": False,
        "is_hot": False,
        "priority_score": 60,
        "commission_rate": 2.0,
        "thumbnail_url": "https://placehold.co/400x250/9B59B6/FFFFFF?text=Kancelář+60m²"
    },
    {
        "id": 16,
        "property_type": "warehouse",
        "location": "Kladno",
        "region": "Čechy",
        "country": "CZ",
        "area_sqm": 900,
        "price_czk_sqm": 88,
        "availability": "2026-02-15",
        "parking_spaces": 0,
        "amenities": ["rampa", "vytapeni"],
        "is_featured": False,
        "is_hot": False,
        "priority_score": 72,
        "commission_rate": 2.0,
        "thumbnail_url": "https://placehold.co/400x250/2C3E50/FFFFFF?text=Sklad+900m²",
        "highway_access": "D6 (6 km)",
        "transport_notes": "Průmyslová zóna Kladno"
    },
    {
        "id": 17,
        "property_type": "warehouse",
        "location": "Hradec Králové",
        "region": "Čechy",
        "country": "CZ",
        "area_sqm": 1100,
        "price_czk_sqm": 82,
        "availability": "2026-03-01",
        "parking_spaces": 0,
        "amenities": ["rampa", "vysoke_stropy_9m"],
        "is_featured": False,
        "is_hot": False,
        "priority_score": 68,
        "commission_rate": 2.0,
        "thumbnail_url": "https://placehold.co/400x250/34495E/FFFFFF?text=Sklad+1100m²",
        "highway_access": "D11 (2 km)",
        "transport_notes": "Logistický uzel východních Čech"
    },
    {
        "id": 18,
        "property_type": "office",
        "location": "Praha 6 – Dejvice",
        "region": "Čechy",
        "country": "CZ",
        "area_sqm": 180,
        "price_czk_sqm": 310,
        "availability": "ihned",
        "parking_spaces": 2,
        "amenities": ["klimatizace", "moderni"],
        "is_featured": True,
        "is_hot": False,
        "priority_score": 82,
        "commission_rate": 2.5,
        "thumbnail_url": "https://placehold.co/400x250/3498DB/FFFFFF?text=⭐+Kancelář+180m²"
    },
    {
        "id": 19,
        "property_type": "office",
        "location": "Liberec – centrum",
        "region": "Čechy",
        "country": "CZ",
        "area_sqm": 140,
        "price_czk_sqm": 190,
        "availability": "2026-02-01",
        "parking_spaces": 1,
        "amenities": ["standard"],
        "is_featured": False,
        "is_hot": False,
        "priority_score": 58,
        "commission_rate": 1.5,
        "thumbnail_url": "https://placehold.co/400x250/1ABC9C/FFFFFF?text=Kancelář+140m²"
    },
    {
        "id": 20,
        "property_type": "office",
        "location": "Praha 3 – Žižkov",
        "region": "Čechy",
        "country": "CZ",
        "area_sqm": 95,
        "price_czk_sqm": 260,
        "availability": "ihned",
        "parking_spaces": 0,
        "amenities": ["open_space", "po_rekonstrukci"],
        "is_featured": False,
        "is_hot": False,
        "priority_score": 64,
        "commission_rate": 2.0,
        "thumbnail_url": "https://placehold.co/400x250/16A085/FFFFFF?text=Kancelář+95m²"
    }
]


def init_database():
    """Initialize database with all properties."""
    print("Initializing database...")

    # Get database and repository
    db = get_database()
    repo = PropertyRepository(db)

    # Check current count
    current_count = repo.get_count()
    print(f"Current properties in database: {current_count}")

    if current_count > 0:
        print("Database already has properties. Clearing...")
        for prop_data in PROPERTIES:
            repo.delete(prop_data["id"])

    # Insert all properties
    inserted = 0
    for prop_data in PROPERTIES:
        prop = Property(**prop_data)
        repo.create(prop)
        inserted += 1
        print(f"  Inserted: {prop.id} - {prop.location} ({prop.region})")

    print(f"\nInserted {inserted} properties")

    # Show summary by region
    all_props = repo.get_all(use_cache=False)
    regions = {}
    for p in all_props:
        region = p.region or "Unknown"
        regions[region] = regions.get(region, 0) + 1

    print("\nProperties by region:")
    for region, count in sorted(regions.items()):
        print(f"  {region}: {count}")

    return inserted


if __name__ == "__main__":
    init_database()
