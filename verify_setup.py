"""
Setup verification script.
Run this to verify all components are working before starting the app.
"""

import sys
from pathlib import Path

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')


def check_imports():
    """Check if all required packages are installed."""
    print("Checking imports...")

    required = [
        ("streamlit", "streamlit"),
        ("langchain", "langchain"),
        ("langchain_openai", "langchain-openai"),
        ("chromadb", "chromadb"),
        ("openai", "openai"),
        ("pydantic", "pydantic"),
        ("dotenv", "python-dotenv"),
    ]

    missing = []
    for module, package in required:
        try:
            __import__(module)
            print(f"  [OK] {package}")
        except ImportError:
            print(f"  [FAIL] {package}")
            missing.append(package)

    if missing:
        print(f"\nMissing packages: {', '.join(missing)}")
        print("Run: pip install -r requirements.txt")
        return False

    return True


def check_env():
    """Check environment variables."""
    print("\nChecking environment...")

    from dotenv import load_dotenv
    import os

    load_dotenv()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("  [FAIL] OPENAI_API_KEY not set")
        print("  Create .env file with your API key")
        return False

    if api_key.startswith("sk-"):
        print("  [OK] OPENAI_API_KEY configured")
    else:
        print("  [WARN] OPENAI_API_KEY format looks unusual")

    print(f"  [OK] Model: {os.getenv('OPENAI_MODEL', 'gpt-4o-mini')}")
    print(f"  [OK] Embedding: {os.getenv('OPENAI_EMBEDDING_MODEL', 'text-embedding-3-small')}")

    return True


def check_data():
    """Check if property data is available."""
    print("\nChecking data...")

    data_file = Path(__file__).parent / "app" / "data" / "properties.json"
    if not data_file.exists():
        print(f"  [FAIL] properties.json not found at {data_file}")
        return False

    import json
    with open(data_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"  [OK] Found {len(data)} properties")

    # Validate structure
    required_fields = ["id", "property_type", "location", "area_sqm", "price_czk_sqm"]
    for prop in data[:1]:
        for field in required_fields:
            if field not in prop:
                print(f"  [FAIL] Missing field: {field}")
                return False

    print("  [OK] Data structure valid")
    return True


def check_models():
    """Check if Pydantic models work."""
    print("\nChecking models...")

    try:
        from app.models import Property, Lead, Broker, ConversationState

        # Test Property
        prop = Property(
            id=1,
            property_type="warehouse",
            location="Praha-vychod",
            area_sqm=500,
            price_czk_sqm=100,
            availability="ihned",
        )
        print(f"  [OK] Property model works (total rent: {prop.total_monthly_rent})")

        # Test Lead
        lead = Lead()
        print(f"  [OK] Lead model works (score: {lead.lead_score})")

        return True
    except Exception as e:
        print(f"  [FAIL] Model error: {e}")
        return False


def check_vectorstore():
    """Check if ChromaDB and embeddings work."""
    print("\nChecking vector store...")

    try:
        from app.rag import PropertyVectorStore

        vs = PropertyVectorStore()
        count = vs.get_collection_count()

        if count == 0:
            print("  [WARN] Vector store empty, indexing...")
            indexed = vs.index_properties()
            print(f"  [OK] Indexed {indexed} properties")
        else:
            print(f"  [OK] Vector store has {count} items")

        return True
    except Exception as e:
        print(f"  [FAIL] Vector store error: {e}")
        return False


def check_retrieval():
    """Check if retrieval works."""
    print("\nChecking retrieval...")

    try:
        from app.rag import PropertyRetriever

        retriever = PropertyRetriever()
        results = retriever.search_properties(
            query="sklad Praha",
            top_k=3
        )

        print(f"  [OK] Retrieved {len(results)} properties for 'sklad Praha'")

        if results:
            print(f"       First result: {results[0].location} ({results[0].area_sqm} m2)")

        return True
    except Exception as e:
        print(f"  [FAIL] Retrieval error: {e}")
        return False


def check_llm():
    """Check if LLM connection works."""
    print("\nChecking LLM connection...")

    try:
        from openai import OpenAI
        from app.config import OPENAI_API_KEY, OPENAI_MODEL

        client = OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": "Say 'Hello' in Czech."}],
            max_tokens=10,
        )

        reply = response.choices[0].message.content
        print(f"  [OK] LLM response: {reply}")

        return True
    except Exception as e:
        print(f"  [FAIL] LLM error: {e}")
        return False


def main():
    print("="*50)
    print("SETUP VERIFICATION")
    print("="*50)

    checks = [
        ("Imports", check_imports),
        ("Environment", check_env),
        ("Data", check_data),
        ("Models", check_models),
        ("Vector Store", check_vectorstore),
        ("Retrieval", check_retrieval),
        ("LLM", check_llm),
    ]

    results = []
    for name, check_fn in checks:
        try:
            results.append((name, check_fn()))
        except Exception as e:
            print(f"  [FAIL] {name} failed: {e}")
            results.append((name, False))

    print("\n" + "="*50)
    print("SUMMARY")
    print("="*50)

    all_passed = True
    for name, passed in results:
        status = "[OK]" if passed else "[FAIL]"
        print(f"  {status} {name}")
        if not passed:
            all_passed = False

    if all_passed:
        print("\nAll checks passed! Run: streamlit run app/main.py")
    else:
        print("\nSome checks failed. Fix issues before running the app.")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
