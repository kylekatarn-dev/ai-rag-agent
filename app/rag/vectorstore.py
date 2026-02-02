from pathlib import Path
import chromadb
from chromadb.config import Settings

from app.config import CHROMA_DIR, CHROMA_COLLECTION_NAME
from app.data.loader import load_properties
from app.models.property import Property
from .embeddings import get_embeddings


class PropertyVectorStore:
    """ChromaDB vector store for properties."""

    def __init__(self):
        self.embeddings = get_embeddings()
        self.client = self._get_client()
        self.collection = self._get_or_create_collection()

    def _get_client(self) -> chromadb.Client:
        """Get or create ChromaDB client."""
        persist_dir = Path(CHROMA_DIR)
        persist_dir.mkdir(parents=True, exist_ok=True)

        return chromadb.PersistentClient(
            path=str(persist_dir),
            settings=Settings(anonymized_telemetry=False)
        )

    def _get_or_create_collection(self):
        """Get or create the properties collection."""
        return self.client.get_or_create_collection(
            name=CHROMA_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"}
        )

    def index_properties(self, properties: list[Property] | None = None) -> int:
        """Index all properties into the vector store."""
        if properties is None:
            properties = load_properties()

        # Clear existing data
        existing = self.collection.get()
        if existing["ids"]:
            self.collection.delete(ids=existing["ids"])

        # Prepare documents
        documents = []
        metadatas = []
        ids = []

        for prop in properties:
            documents.append(prop.to_embedding_text())
            metadatas.append({
                "id": prop.id,
                "property_type": prop.property_type,
                "location": prop.location,
                "location_region": prop.location_region,  # Uses region field or country fallback
                "region": prop.region or "",  # Direct region field
                "country": prop.country,
                "area_sqm": prop.area_sqm,
                "price_czk_sqm": prop.price_czk_sqm,
                "total_monthly_rent": prop.total_monthly_rent,
                "is_available_now": prop.is_available_now,
                "is_featured": prop.is_featured,
                "is_hot": prop.is_hot,
                "priority_score": prop.priority_score,
            })
            ids.append(f"property_{prop.id}")

        # Generate embeddings and add to collection
        embeddings = self.embeddings.embed_documents(documents)

        self.collection.add(
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
            ids=ids
        )

        return len(properties)

    def search(
        self,
        query: str,
        property_type: str | None = None,
        location_region: str | None = None,
        min_area: int | None = None,
        max_area: int | None = None,
        max_price: int | None = None,
        available_now: bool | None = None,
        top_k: int = 5,
    ) -> list[dict]:
        """Search for properties matching query and filters."""

        # Build where clause for metadata filtering
        where_clauses = []

        if property_type:
            where_clauses.append({"property_type": {"$eq": property_type}})

        if location_region:
            where_clauses.append({"location_region": {"$eq": location_region}})

        if min_area is not None:
            where_clauses.append({"area_sqm": {"$gte": min_area}})

        if max_area is not None:
            where_clauses.append({"area_sqm": {"$lte": max_area}})

        if max_price is not None:
            where_clauses.append({"price_czk_sqm": {"$lte": max_price}})

        if available_now is True:
            where_clauses.append({"is_available_now": {"$eq": True}})

        # Combine where clauses
        where = None
        if len(where_clauses) == 1:
            where = where_clauses[0]
        elif len(where_clauses) > 1:
            where = {"$and": where_clauses}

        # Generate query embedding
        query_embedding = self.embeddings.embed_query(query)

        # Search
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"]
        )

        # Format results
        formatted = []
        if results["ids"] and results["ids"][0]:
            for i, id in enumerate(results["ids"][0]):
                formatted.append({
                    "id": results["metadatas"][0][i]["id"],
                    "document": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "distance": results["distances"][0][i],
                    "similarity": 1 - results["distances"][0][i],  # Convert distance to similarity
                })

        # Sort by priority_score (business ranking) while maintaining relevance
        formatted.sort(
            key=lambda x: (x["similarity"] * 0.6 + x["metadata"]["priority_score"] / 100 * 0.4),
            reverse=True
        )

        return formatted

    def get_collection_count(self) -> int:
        """Get number of items in collection."""
        return self.collection.count()

    def is_indexed(self) -> bool:
        """Check if properties are already indexed."""
        return self.collection.count() > 0
