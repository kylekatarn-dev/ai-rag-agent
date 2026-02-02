"""
Repository Classes.

Provides data access patterns for properties, leads, conversations, and sessions.
"""

from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4
import hashlib
import secrets
import json
from pathlib import Path

from app.models.lead import Lead, LeadQuality, CustomerType
from app.models.conversation import ConversationState, Message
from app.models.property import Property, PropertyImage
from app.utils import get_logger
from .database import Database, get_database

logger = get_logger(__name__)


class LeadRepository:
    """
    Repository for Lead persistence.

    Handles CRUD operations and queries for leads.
    """

    def __init__(self, db: Optional[Database] = None):
        self.db = db or get_database()

    def save(self, lead: Lead, session_id: Optional[str] = None) -> str:
        """
        Save or update a lead.

        Args:
            lead: Lead model to save
            session_id: Associated session ID

        Returns:
            Lead ID
        """
        data = {
            "id": lead.id,
            "session_id": session_id,
            "updated_at": datetime.now().isoformat(),
            "name": lead.name,
            "email": lead.email,
            "phone": lead.phone,
            "company": lead.company,
            "preferred_contact_method": lead.preferred_contact_method,
            "preferred_call_time": lead.preferred_call_time,
            "wants_notifications": lead.wants_notifications,
            "wants_broker_contact": lead.wants_broker_contact,
            "notification_criteria": self.db.to_json(lead.notification_criteria),
            "property_type": lead.property_type,
            "min_area_sqm": lead.min_area_sqm,
            "max_area_sqm": lead.max_area_sqm,
            "preferred_locations": self.db.to_json(lead.preferred_locations),
            "max_price_czk_sqm": lead.max_price_czk_sqm,
            "move_in_date": lead.move_in_date.isoformat() if lead.move_in_date else None,
            "move_in_urgency": lead.move_in_urgency,
            "required_amenities": self.db.to_json(lead.required_amenities),
            "parking_needed": lead.parking_needed,
            "lead_score": lead.lead_score,
            "lead_quality": lead.lead_quality.value if lead.lead_quality else "cold",
            "customer_type": lead.customer_type.value if lead.customer_type else None,
            "matched_properties": self.db.to_json(lead.matched_properties),
            "best_match_id": lead.best_match_id,
            "status": lead.status,
            "assigned_broker_id": lead.assigned_broker_id,
            "conversation_summary": lead.conversation_summary,
            "key_objections": self.db.to_json(lead.key_objections),
            "follow_up_actions": self.db.to_json(lead.follow_up_actions),
        }

        # Check if exists
        existing = self.db.fetch_one(
            "SELECT id FROM leads WHERE id = ?",
            (lead.id,)
        )

        if existing:
            self.db.update("leads", data, "id = ?", (lead.id,))
            logger.debug(f"Updated lead: {lead.id}")
        else:
            data["created_at"] = lead.created_at.isoformat()
            self.db.insert("leads", data)
            logger.debug(f"Created lead: {lead.id}")

        return lead.id

    def get(self, lead_id: str) -> Optional[Lead]:
        """Get lead by ID."""
        row = self.db.fetch_one(
            "SELECT * FROM leads WHERE id = ?",
            (lead_id,)
        )

        if not row:
            return None

        return self._row_to_lead(row)

    def get_by_session(self, session_id: str) -> Optional[Lead]:
        """Get lead by session ID."""
        row = self.db.fetch_one(
            "SELECT * FROM leads WHERE session_id = ? ORDER BY created_at DESC LIMIT 1",
            (session_id,)
        )

        if not row:
            return None

        return self._row_to_lead(row)

    def get_by_email(self, email: str) -> list[Lead]:
        """Get leads by email."""
        rows = self.db.fetch_all(
            "SELECT * FROM leads WHERE email = ? ORDER BY created_at DESC",
            (email,)
        )
        return [self._row_to_lead(row) for row in rows]

    def get_by_quality(self, quality: LeadQuality, limit: int = 100) -> list[Lead]:
        """Get leads by quality tier."""
        rows = self.db.fetch_all(
            "SELECT * FROM leads WHERE lead_quality = ? ORDER BY lead_score DESC LIMIT ?",
            (quality.value, limit)
        )
        return [self._row_to_lead(row) for row in rows]

    def get_recent(self, hours: int = 24, limit: int = 100) -> list[Lead]:
        """Get recent leads."""
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        rows = self.db.fetch_all(
            "SELECT * FROM leads WHERE created_at >= ? ORDER BY created_at DESC LIMIT ?",
            (cutoff, limit)
        )
        return [self._row_to_lead(row) for row in rows]

    def get_hot_leads(self, limit: int = 50) -> list[Lead]:
        """Get hot leads for immediate follow-up."""
        return self.get_by_quality(LeadQuality.HOT, limit)

    def delete(self, lead_id: str) -> bool:
        """Delete a lead."""
        count = self.db.delete("leads", "id = ?", (lead_id,))
        return count > 0

    def _row_to_lead(self, row) -> Lead:
        """Convert database row to Lead model."""
        return Lead(
            id=row["id"],
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.now(),
            name=row["name"],
            email=row["email"],
            phone=row["phone"],
            company=row["company"],
            preferred_contact_method=row["preferred_contact_method"],
            preferred_call_time=row["preferred_call_time"],
            wants_notifications=bool(row["wants_notifications"]),
            wants_broker_contact=bool(row["wants_broker_contact"]),
            notification_criteria=self.db.from_json(row["notification_criteria"], {}),
            property_type=row["property_type"],
            min_area_sqm=row["min_area_sqm"],
            max_area_sqm=row["max_area_sqm"],
            preferred_locations=self.db.from_json(row["preferred_locations"], []),
            max_price_czk_sqm=row["max_price_czk_sqm"],
            move_in_date=datetime.fromisoformat(row["move_in_date"]).date() if row["move_in_date"] else None,
            move_in_urgency=row["move_in_urgency"],
            required_amenities=self.db.from_json(row["required_amenities"], []),
            parking_needed=row["parking_needed"] or 0,
            lead_score=row["lead_score"] or 0,
            lead_quality=LeadQuality(row["lead_quality"]) if row["lead_quality"] else LeadQuality.COLD,
            customer_type=CustomerType(row["customer_type"]) if row["customer_type"] else None,
            matched_properties=self.db.from_json(row["matched_properties"], []),
            best_match_id=row["best_match_id"],
            status=row["status"] or "new",
            assigned_broker_id=row["assigned_broker_id"],
            conversation_summary=row["conversation_summary"] or "",
            key_objections=self.db.from_json(row["key_objections"], []),
            follow_up_actions=self.db.from_json(row["follow_up_actions"], []),
        )


class ConversationRepository:
    """
    Repository for Conversation persistence.

    Handles CRUD operations for conversations and messages.
    """

    def __init__(self, db: Optional[Database] = None):
        self.db = db or get_database()

    def save(self, state: ConversationState, conversation_id: str, session_id: str) -> str:
        """
        Save or update a conversation state.

        Args:
            state: ConversationState to save
            conversation_id: Conversation ID
            session_id: Associated session ID

        Returns:
            Conversation ID
        """
        data = {
            "id": conversation_id,
            "session_id": session_id,
            "updated_at": datetime.now().isoformat(),
            "current_phase": state.current_phase,
            "properties_shown": self.db.to_json(state.properties_shown),
            "questions_asked": self.db.to_json(state.questions_asked),
            "info_gathered": self.db.to_json(state.info_gathered),
            "search_performed": state.search_performed,
            "recommendations_made": state.recommendations_made,
            "contact_requested": state.contact_requested,
            "summary_generated": state.summary_generated,
        }

        # Check if exists
        existing = self.db.fetch_one(
            "SELECT id FROM conversations WHERE id = ?",
            (conversation_id,)
        )

        if existing:
            self.db.update("conversations", data, "id = ?", (conversation_id,))
        else:
            data["created_at"] = datetime.now().isoformat()
            self.db.insert("conversations", data)

        # Save messages
        self._save_messages(conversation_id, state.messages)

        logger.debug(f"Saved conversation: {conversation_id}")
        return conversation_id

    def _save_messages(self, conversation_id: str, messages: list[Message]) -> None:
        """Save messages for a conversation."""
        # Get existing message count
        existing = self.db.fetch_one(
            "SELECT COUNT(*) as count FROM messages WHERE conversation_id = ?",
            (conversation_id,)
        )
        existing_count = existing["count"] if existing else 0

        # Only save new messages
        new_messages = messages[existing_count:]

        for msg in new_messages:
            self.db.insert("messages", {
                "conversation_id": conversation_id,
                "role": msg.role,
                "content": msg.content,
                "timestamp": msg.timestamp.isoformat(),
                "properties_mentioned": self.db.to_json(msg.properties_mentioned),
                "tool_calls": self.db.to_json(msg.tool_calls),
                "tokens_estimated": msg.estimated_tokens,
            })

    def get(self, conversation_id: str) -> Optional[ConversationState]:
        """Get conversation by ID."""
        row = self.db.fetch_one(
            "SELECT * FROM conversations WHERE id = ?",
            (conversation_id,)
        )

        if not row:
            return None

        return self._row_to_state(row)

    def get_by_session(self, session_id: str) -> Optional[ConversationState]:
        """Get most recent conversation for session."""
        row = self.db.fetch_one(
            "SELECT * FROM conversations WHERE session_id = ? ORDER BY updated_at DESC LIMIT 1",
            (session_id,)
        )

        if not row:
            return None

        return self._row_to_state(row)

    def get_messages(self, conversation_id: str) -> list[Message]:
        """Get messages for a conversation."""
        rows = self.db.fetch_all(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY id ASC",
            (conversation_id,)
        )

        return [
            Message(
                role=row["role"],
                content=row["content"],
                timestamp=datetime.fromisoformat(row["timestamp"]) if row["timestamp"] else datetime.now(),
                properties_mentioned=self.db.from_json(row["properties_mentioned"], []),
                tool_calls=self.db.from_json(row["tool_calls"], []),
            )
            for row in rows
        ]

    def delete(self, conversation_id: str) -> bool:
        """Delete a conversation and its messages."""
        self.db.delete("messages", "conversation_id = ?", (conversation_id,))
        count = self.db.delete("conversations", "id = ?", (conversation_id,))
        return count > 0

    def _row_to_state(self, row) -> ConversationState:
        """Convert database row to ConversationState."""
        messages = self.get_messages(row["id"])

        return ConversationState(
            messages=messages,
            current_phase=row["current_phase"] or "greeting",
            properties_shown=self.db.from_json(row["properties_shown"], []),
            questions_asked=self.db.from_json(row["questions_asked"], []),
            info_gathered=self.db.from_json(row["info_gathered"], {}),
            search_performed=bool(row["search_performed"]),
            recommendations_made=bool(row["recommendations_made"]),
            contact_requested=bool(row["contact_requested"]),
            summary_generated=bool(row["summary_generated"]),
        )


class SessionRepository:
    """
    Repository for User Session management.

    Handles session creation, validation, and user authentication.
    """

    SESSION_DURATION_HOURS = 24

    def __init__(self, db: Optional[Database] = None):
        self.db = db or get_database()

    def create_session(
        self,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> str:
        """
        Create a new session.

        Args:
            user_id: Optional user ID for authenticated sessions
            ip_address: Client IP address
            user_agent: Client user agent

        Returns:
            Session ID (token)
        """
        session_id = secrets.token_urlsafe(32)
        expires_at = datetime.now() + timedelta(hours=self.SESSION_DURATION_HOURS)

        self.db.insert("sessions", {
            "id": session_id,
            "user_id": user_id,
            "created_at": datetime.now().isoformat(),
            "last_activity": datetime.now().isoformat(),
            "expires_at": expires_at.isoformat(),
            "ip_address": ip_address,
            "user_agent": user_agent,
        })

        logger.debug(f"Created session: {session_id[:16]}...")
        return session_id

    def validate_session(self, session_id: str) -> Optional[dict]:
        """
        Validate a session and update last activity.

        Args:
            session_id: Session token to validate

        Returns:
            Session data if valid, None otherwise
        """
        row = self.db.fetch_one(
            "SELECT * FROM sessions WHERE id = ?",
            (session_id,)
        )

        if not row:
            return None

        # Check expiration
        expires_at = datetime.fromisoformat(row["expires_at"])
        if datetime.now() > expires_at:
            self.delete_session(session_id)
            return None

        # Update last activity
        self.db.update(
            "sessions",
            {"last_activity": datetime.now().isoformat()},
            "id = ?",
            (session_id,)
        )

        return dict(row)

    def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        count = self.db.delete("sessions", "id = ?", (session_id,))
        return count > 0

    def get_user_sessions(self, user_id: str) -> list[dict]:
        """Get all sessions for a user."""
        rows = self.db.fetch_all(
            "SELECT * FROM sessions WHERE user_id = ? ORDER BY last_activity DESC",
            (user_id,)
        )
        return [dict(row) for row in rows]

    def cleanup_expired(self) -> int:
        """Delete expired sessions."""
        count = self.db.delete(
            "sessions",
            "expires_at < ?",
            (datetime.now().isoformat(),)
        )
        if count > 0:
            logger.info(f"Cleaned up {count} expired sessions")
        return count

    # User management methods

    def create_user(
        self,
        email: str,
        password: str,
        name: Optional[str] = None,
    ) -> Optional[str]:
        """
        Create a new user.

        Args:
            email: User email (unique)
            password: Plain text password (will be hashed)
            name: Optional user name

        Returns:
            User ID if created, None if email exists
        """
        # Check if email exists
        existing = self.db.fetch_one(
            "SELECT id FROM users WHERE email = ?",
            (email,)
        )
        if existing:
            return None

        user_id = str(uuid4())
        password_hash = self._hash_password(password)

        self.db.insert("users", {
            "id": user_id,
            "email": email,
            "password_hash": password_hash,
            "name": name,
            "created_at": datetime.now().isoformat(),
            "is_active": True,
        })

        logger.info(f"Created user: {email}")
        return user_id

    def authenticate_user(self, email: str, password: str) -> Optional[str]:
        """
        Authenticate a user.

        Args:
            email: User email
            password: Plain text password

        Returns:
            User ID if authenticated, None otherwise
        """
        row = self.db.fetch_one(
            "SELECT * FROM users WHERE email = ? AND is_active = 1",
            (email,)
        )

        if not row:
            return None

        if not self._verify_password(password, row["password_hash"]):
            return None

        # Update last login
        self.db.update(
            "users",
            {"last_login": datetime.now().isoformat()},
            "id = ?",
            (row["id"],)
        )

        return row["id"]

    def get_user(self, user_id: str) -> Optional[dict]:
        """Get user by ID."""
        row = self.db.fetch_one(
            "SELECT id, email, name, created_at, last_login, is_active FROM users WHERE id = ?",
            (user_id,)
        )
        return dict(row) if row else None

    def _hash_password(self, password: str) -> str:
        """Hash a password using SHA-256 with salt."""
        salt = secrets.token_hex(16)
        hash_obj = hashlib.sha256((salt + password).encode())
        return f"{salt}${hash_obj.hexdigest()}"

    def _verify_password(self, password: str, password_hash: str) -> bool:
        """Verify a password against its hash."""
        try:
            salt, hash_value = password_hash.split("$")
            hash_obj = hashlib.sha256((salt + password).encode())
            return hash_obj.hexdigest() == hash_value
        except ValueError:
            return False


class PropertyRepository:
    """
    Repository for Property persistence.

    Handles CRUD operations, queries, and sync from JSON for properties.
    """

    def __init__(self, db: Optional[Database] = None):
        self.db = db or get_database()
        self._cache: dict[int, Property] = {}
        self._cache_valid = False

    def get_all(self, use_cache: bool = True) -> list[Property]:
        """
        Get all properties.

        Args:
            use_cache: Whether to use cached results

        Returns:
            List of all properties
        """
        if use_cache and self._cache_valid and self._cache:
            return list(self._cache.values())

        rows = self.db.fetch_all(
            "SELECT * FROM properties ORDER BY priority_score DESC, id ASC"
        )

        properties = []
        for row in rows:
            prop = self._row_to_property(row)
            properties.append(prop)
            self._cache[prop.id] = prop

        self._cache_valid = True
        return properties

    def get_by_id(self, property_id: int) -> Optional[Property]:
        """Get property by ID."""
        if self._cache_valid and property_id in self._cache:
            return self._cache[property_id]

        row = self.db.fetch_one(
            "SELECT * FROM properties WHERE id = ?",
            (property_id,)
        )

        if not row:
            return None

        prop = self._row_to_property(row)
        self._cache[prop.id] = prop
        return prop

    def search(
        self,
        property_type: Optional[str] = None,
        location: Optional[str] = None,
        region: Optional[str] = None,
        country: Optional[str] = None,
        min_area: Optional[int] = None,
        max_area: Optional[int] = None,
        max_price: Optional[int] = None,
        available_now: Optional[bool] = None,
        is_featured: Optional[bool] = None,
        is_hot: Optional[bool] = None,
        limit: int = 100,
    ) -> list[Property]:
        """
        Search properties with filters.

        Args:
            property_type: Filter by type (warehouse/office)
            location: Filter by location (partial match)
            region: Filter by region (e.g., "Morava", "Čechy")
            country: Filter by country code (e.g., "CZ", "SK")
            min_area: Minimum area in sqm
            max_area: Maximum area in sqm
            max_price: Maximum price per sqm
            available_now: Filter immediately available
            is_featured: Filter featured properties
            is_hot: Filter hot/urgent properties
            limit: Maximum results

        Returns:
            List of matching properties
        """
        query = "SELECT * FROM properties WHERE 1=1"
        params = []

        if property_type:
            query += " AND property_type = ?"
            params.append(property_type)

        if location:
            query += " AND location LIKE ?"
            params.append(f"%{location}%")

        if region:
            query += " AND region = ?"
            params.append(region)

        if country:
            query += " AND country = ?"
            params.append(country)

        if min_area is not None:
            query += " AND area_sqm >= ?"
            params.append(min_area)

        if max_area is not None:
            query += " AND area_sqm <= ?"
            params.append(max_area)

        if max_price is not None:
            query += " AND price_czk_sqm <= ?"
            params.append(max_price)

        if available_now is True:
            query += " AND LOWER(availability) = 'ihned'"

        if is_featured is not None:
            query += " AND is_featured = ?"
            params.append(1 if is_featured else 0)

        if is_hot is not None:
            query += " AND is_hot = ?"
            params.append(1 if is_hot else 0)

        query += " ORDER BY priority_score DESC, id ASC LIMIT ?"
        params.append(limit)

        rows = self.db.fetch_all(query, tuple(params))
        return [self._row_to_property(row) for row in rows]

    def get_by_type(self, property_type: str) -> list[Property]:
        """Get all properties of a specific type."""
        return self.search(property_type=property_type)

    def get_featured(self) -> list[Property]:
        """Get all featured properties."""
        return self.search(is_featured=True)

    def get_hot(self) -> list[Property]:
        """Get all hot/urgent properties."""
        return self.search(is_hot=True)

    def get_available_now(self) -> list[Property]:
        """Get all immediately available properties."""
        return self.search(available_now=True)

    def create(self, prop: Property) -> int:
        """
        Create a new property.

        Args:
            prop: Property to create

        Returns:
            Property ID
        """
        data = self._property_to_data(prop)

        self.db.insert("properties", data)

        # Save images
        self._save_images(prop.id, prop.images)

        # Invalidate cache
        self._cache_valid = False
        self._cache.pop(prop.id, None)

        logger.info(f"Created property: {prop.id}")
        return prop.id

    def update(self, prop: Property) -> bool:
        """
        Update an existing property.

        Args:
            prop: Property with updated data

        Returns:
            True if updated, False if not found
        """
        data = self._property_to_data(prop)
        data["last_updated"] = datetime.now().isoformat()

        count = self.db.update("properties", data, "id = ?", (prop.id,))

        if count > 0:
            # Update images
            self.db.delete("property_images", "property_id = ?", (prop.id,))
            self._save_images(prop.id, prop.images)

            # Invalidate cache
            self._cache_valid = False
            self._cache.pop(prop.id, None)

            logger.info(f"Updated property: {prop.id}")
            return True

        return False

    def delete(self, property_id: int) -> bool:
        """
        Delete a property.

        Args:
            property_id: ID of property to delete

        Returns:
            True if deleted
        """
        # Images are deleted by CASCADE
        count = self.db.delete("properties", "id = ?", (property_id,))

        if count > 0:
            self._cache_valid = False
            self._cache.pop(property_id, None)
            logger.info(f"Deleted property: {property_id}")
            return True

        return False

    def sync_from_json(self, json_path: Optional[str] = None) -> int:
        """
        Sync properties from JSON file to database.

        Args:
            json_path: Path to properties.json file

        Returns:
            Number of properties synced
        """
        if json_path is None:
            json_path = Path(__file__).parent.parent / "data" / "properties.json"
        else:
            json_path = Path(json_path)

        if not json_path.exists():
            logger.error(f"Properties JSON not found: {json_path}")
            return 0

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        count = 0
        for item in data:
            prop = Property(**item)

            # Check if exists
            existing = self.db.fetch_one(
                "SELECT id FROM properties WHERE id = ?",
                (prop.id,)
            )

            if existing:
                self.update(prop)
            else:
                self.create(prop)

            count += 1

        self._cache_valid = False
        logger.info(f"Synced {count} properties from JSON")
        return count

    def get_count(self) -> int:
        """Get total property count."""
        row = self.db.fetch_one("SELECT COUNT(*) as count FROM properties")
        return row["count"] if row else 0

    def get_market_stats(self) -> dict:
        """Get market statistics."""
        warehouses = self.search(property_type="warehouse", limit=1000)
        offices = self.search(property_type="office", limit=1000)

        return {
            "warehouse": {
                "count": len(warehouses),
                "avg_price": sum(p.price_czk_sqm for p in warehouses) // len(warehouses) if warehouses else 0,
                "min_price": min(p.price_czk_sqm for p in warehouses) if warehouses else 0,
                "max_price": max(p.price_czk_sqm for p in warehouses) if warehouses else 0,
                "avg_area": sum(p.area_sqm for p in warehouses) // len(warehouses) if warehouses else 0,
            },
            "office": {
                "count": len(offices),
                "avg_price": sum(p.price_czk_sqm for p in offices) // len(offices) if offices else 0,
                "min_price": min(p.price_czk_sqm for p in offices) if offices else 0,
                "max_price": max(p.price_czk_sqm for p in offices) if offices else 0,
                "avg_area": sum(p.area_sqm for p in offices) // len(offices) if offices else 0,
            },
            "total": len(warehouses) + len(offices),
        }

    def _save_images(self, property_id: int, images: list[PropertyImage]) -> None:
        """Save property images."""
        for i, img in enumerate(images):
            self.db.insert("property_images", {
                "property_id": property_id,
                "url": img.url,
                "alt": img.alt,
                "is_primary": 1 if img.is_primary else 0,
                "display_order": img.order if img.order else i,
                "width": img.width,
                "height": img.height,
            })

    def _get_images(self, property_id: int) -> list[PropertyImage]:
        """Get images for a property."""
        rows = self.db.fetch_all(
            "SELECT * FROM property_images WHERE property_id = ? ORDER BY display_order ASC",
            (property_id,)
        )

        return [
            PropertyImage(
                url=row["url"],
                alt=row["alt"] or "",
                is_primary=bool(row["is_primary"]),
                order=row["display_order"] or 0,
                width=row["width"],
                height=row["height"],
            )
            for row in rows
        ]

    def _property_to_data(self, prop: Property) -> dict:
        """Convert Property to database row data."""
        return {
            "id": prop.id,
            "property_type": prop.property_type,
            "location": prop.location,
            "region": prop.region,
            "country": prop.country,
            "area_sqm": prop.area_sqm,
            "price_czk_sqm": prop.price_czk_sqm,
            "availability": prop.availability,
            "parking_spaces": prop.parking_spaces,
            "amenities": self.db.to_json(prop.amenities),
            "thumbnail_url": prop.thumbnail_url,
            "virtual_tour_url": prop.virtual_tour_url,
            "is_featured": 1 if prop.is_featured else 0,
            "is_hot": 1 if prop.is_hot else 0,
            "priority_score": prop.priority_score,
            "commission_rate": prop.commission_rate,
            "description": prop.description,
            "floor": prop.floor,
            "building_class": prop.building_class,
            "energy_rating": prop.energy_rating,
            "highway_access": prop.highway_access,
            "transport_notes": prop.transport_notes,
            "last_updated": datetime.now().isoformat(),
        }

    def _row_to_property(self, row) -> Property:
        """Convert database row to Property model."""
        images = self._get_images(row["id"])

        # Handle optional region/country fields gracefully
        region = row["region"] if "region" in row.keys() else None
        country = row["country"] if "country" in row.keys() else "CZ"

        return Property(
            id=row["id"],
            property_type=row["property_type"],
            location=row["location"],
            region=region,
            country=country or "CZ",
            area_sqm=row["area_sqm"],
            price_czk_sqm=row["price_czk_sqm"],
            availability=row["availability"],
            parking_spaces=row["parking_spaces"] or 0,
            amenities=self.db.from_json(row["amenities"], []),
            images=images,
            thumbnail_url=row["thumbnail_url"],
            virtual_tour_url=row["virtual_tour_url"],
            is_featured=bool(row["is_featured"]),
            is_hot=bool(row["is_hot"]),
            priority_score=row["priority_score"] or 0,
            commission_rate=row["commission_rate"] or 0.0,
            description=row["description"],
            floor=row["floor"],
            building_class=row["building_class"],
            energy_rating=row["energy_rating"],
            highway_access=row["highway_access"],
            transport_notes=row["transport_notes"],
            last_updated=row["last_updated"] if isinstance(row["last_updated"], datetime) else (datetime.fromisoformat(row["last_updated"]) if row["last_updated"] else None),
        )


# Singleton property repository
_property_repo: PropertyRepository | None = None


def get_property_repository() -> PropertyRepository:
    """Get singleton property repository instance."""
    global _property_repo
    if _property_repo is None:
        _property_repo = PropertyRepository()
    return _property_repo
