"""
Database Module.

Provides SQLite database connection and schema management.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional, Generator
import json
import threading

from app.utils import get_logger

logger = get_logger(__name__)


# Register custom timestamp converter that handles both formats:
# - SQLite default: "YYYY-MM-DD HH:MM:SS.ffffff"
# - ISO 8601: "YYYY-MM-DDTHH:MM:SS.ffffff"
def _convert_timestamp(val: bytes) -> datetime:
    """Convert timestamp bytes to datetime, handling both space and T separators."""
    val_str = val.decode('utf-8')
    # Replace T with space to normalize ISO 8601 format
    val_str = val_str.replace('T', ' ')
    # Handle with or without microseconds
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(val_str, fmt)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse timestamp: {val}")


# Register the custom converter
sqlite3.register_converter("TIMESTAMP", _convert_timestamp)


# Database schema
SCHEMA = """
-- Properties table (core property data)
CREATE TABLE IF NOT EXISTS properties (
    id INTEGER PRIMARY KEY,
    property_type TEXT NOT NULL CHECK(property_type IN ('warehouse', 'office')),
    location TEXT NOT NULL,
    region TEXT,  -- e.g., "Morava", "Čechy", "Slezsko", "Slovensko" (nullable)
    country TEXT DEFAULT 'CZ',  -- Country code
    area_sqm INTEGER NOT NULL,
    price_czk_sqm INTEGER NOT NULL,
    availability TEXT NOT NULL,
    parking_spaces INTEGER DEFAULT 0,
    amenities TEXT,  -- JSON array

    -- Image fields
    thumbnail_url TEXT,
    virtual_tour_url TEXT,

    -- Business priority
    is_featured BOOLEAN DEFAULT 0,
    is_hot BOOLEAN DEFAULT 0,
    priority_score INTEGER DEFAULT 0,
    commission_rate REAL DEFAULT 0.0,

    -- Extended fields
    description TEXT,
    floor INTEGER,
    building_class TEXT CHECK(building_class IN ('A', 'B', 'C') OR building_class IS NULL),
    energy_rating TEXT,

    -- Transport/logistics
    highway_access TEXT,
    transport_notes TEXT,

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Property images table
CREATE TABLE IF NOT EXISTS property_images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    property_id INTEGER NOT NULL,
    url TEXT NOT NULL,
    alt TEXT DEFAULT '',
    is_primary BOOLEAN DEFAULT 0,
    display_order INTEGER DEFAULT 0,
    width INTEGER,
    height INTEGER,
    FOREIGN KEY (property_id) REFERENCES properties(id) ON DELETE CASCADE
);

-- Users/Sessions table
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE,
    password_hash TEXT,
    name TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP,
    is_active BOOLEAN DEFAULT 1
);

-- Sessions table
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_activity TIMESTAMP,
    expires_at TIMESTAMP,
    ip_address TEXT,
    user_agent TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Leads table
CREATE TABLE IF NOT EXISTS leads (
    id TEXT PRIMARY KEY,
    session_id TEXT,
    user_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP,

    -- Contact info
    name TEXT,
    email TEXT,
    phone TEXT,
    company TEXT,

    -- Contact preferences
    preferred_contact_method TEXT,
    preferred_call_time TEXT,
    wants_notifications BOOLEAN DEFAULT 0,
    wants_broker_contact BOOLEAN DEFAULT 0,
    notification_criteria TEXT,  -- JSON

    -- Requirements
    property_type TEXT,
    min_area_sqm INTEGER,
    max_area_sqm INTEGER,
    preferred_locations TEXT,  -- JSON array
    max_price_czk_sqm INTEGER,
    move_in_date DATE,
    move_in_urgency TEXT,
    required_amenities TEXT,  -- JSON array
    parking_needed INTEGER DEFAULT 0,

    -- Qualification
    lead_score INTEGER DEFAULT 0,
    lead_quality TEXT DEFAULT 'cold',
    customer_type TEXT,

    -- Matching
    matched_properties TEXT,  -- JSON array
    best_match_id INTEGER,

    -- Status
    status TEXT DEFAULT 'new',
    assigned_broker_id INTEGER,

    -- Conversation
    conversation_summary TEXT,
    key_objections TEXT,  -- JSON array
    follow_up_actions TEXT,  -- JSON array

    FOREIGN KEY (session_id) REFERENCES sessions(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Conversations table
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    lead_id TEXT,
    user_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP,

    -- State
    current_phase TEXT DEFAULT 'greeting',
    properties_shown TEXT,  -- JSON array
    questions_asked TEXT,  -- JSON array
    info_gathered TEXT,  -- JSON object

    -- Tracking
    search_performed BOOLEAN DEFAULT 0,
    recommendations_made BOOLEAN DEFAULT 0,
    contact_requested BOOLEAN DEFAULT 0,
    summary_generated BOOLEAN DEFAULT 0,

    FOREIGN KEY (session_id) REFERENCES sessions(id),
    FOREIGN KEY (lead_id) REFERENCES leads(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Messages table
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Metadata
    properties_mentioned TEXT,  -- JSON array
    tool_calls TEXT,  -- JSON array
    tokens_estimated INTEGER,

    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);

-- Property alerts table
CREATE TABLE IF NOT EXISTS property_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    lead_id TEXT,
    email TEXT NOT NULL,
    name TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT 1,
    last_sent TIMESTAMP,

    -- Criteria
    property_type TEXT,
    min_area INTEGER,
    max_area INTEGER,
    locations TEXT,  -- JSON array
    max_price INTEGER,

    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (lead_id) REFERENCES leads(id)
);

-- Analytics events table
CREATE TABLE IF NOT EXISTS analytics_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    session_id TEXT,
    lead_id TEXT,
    user_id TEXT,
    properties TEXT,  -- JSON object

    FOREIGN KEY (session_id) REFERENCES sessions(id),
    FOREIGN KEY (lead_id) REFERENCES leads(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_properties_type ON properties(property_type);
CREATE INDEX IF NOT EXISTS idx_properties_location ON properties(location);
CREATE INDEX IF NOT EXISTS idx_properties_price ON properties(price_czk_sqm);
CREATE INDEX IF NOT EXISTS idx_properties_area ON properties(area_sqm);
CREATE INDEX IF NOT EXISTS idx_properties_featured ON properties(is_featured);
CREATE INDEX IF NOT EXISTS idx_properties_hot ON properties(is_hot);
CREATE INDEX IF NOT EXISTS idx_property_images_property ON property_images(property_id);
CREATE INDEX IF NOT EXISTS idx_leads_session ON leads(session_id);
CREATE INDEX IF NOT EXISTS idx_leads_email ON leads(email);
CREATE INDEX IF NOT EXISTS idx_leads_quality ON leads(lead_quality);
CREATE INDEX IF NOT EXISTS idx_conversations_session ON conversations(session_id);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_analytics_type ON analytics_events(event_type);
CREATE INDEX IF NOT EXISTS idx_analytics_session ON analytics_events(session_id);
"""


class Database:
    """
    SQLite database manager with connection pooling and thread safety.

    Features:
    - Connection pooling per thread
    - Automatic schema creation
    - Transaction support
    - JSON serialization helpers
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize database.

        Args:
            db_path: Path to SQLite database file. Defaults to ./data/prochazka.db
        """
        if db_path is None:
            db_path = Path(__file__).parent.parent.parent / "data" / "prochazka.db"

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._local = threading.local()
        self._lock = threading.Lock()

        # Initialize schema
        self._init_schema()

        logger.info(f"Database initialized: {self.db_path}")

    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            self._local.connection = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
                detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
            )
            self._local.connection.row_factory = sqlite3.Row
            # Enable foreign keys
            self._local.connection.execute("PRAGMA foreign_keys = ON")

        return self._local.connection

    def _init_schema(self) -> None:
        """Initialize database schema."""
        with self.transaction() as conn:
            conn.executescript(SCHEMA)
        logger.debug("Database schema initialized")

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """
        Context manager for database transactions.

        Usage:
            with db.transaction() as conn:
                conn.execute("INSERT INTO ...")
        """
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Transaction failed: {e}")
            raise

    def execute(
        self,
        query: str,
        params: tuple = (),
    ) -> sqlite3.Cursor:
        """Execute a query and return cursor."""
        conn = self._get_connection()
        return conn.execute(query, params)

    def execute_many(
        self,
        query: str,
        params_list: list[tuple],
    ) -> sqlite3.Cursor:
        """Execute a query with multiple parameter sets."""
        conn = self._get_connection()
        return conn.executemany(query, params_list)

    def fetch_one(
        self,
        query: str,
        params: tuple = (),
    ) -> Optional[sqlite3.Row]:
        """Fetch a single row."""
        cursor = self.execute(query, params)
        return cursor.fetchone()

    def fetch_all(
        self,
        query: str,
        params: tuple = (),
    ) -> list[sqlite3.Row]:
        """Fetch all rows."""
        cursor = self.execute(query, params)
        return cursor.fetchall()

    def insert(
        self,
        table: str,
        data: dict,
    ) -> int:
        """
        Insert a row and return the last row id.

        Args:
            table: Table name
            data: Dictionary of column -> value

        Returns:
            Last inserted row id
        """
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?" for _ in data])
        query = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"

        with self.transaction() as conn:
            cursor = conn.execute(query, tuple(data.values()))
            return cursor.lastrowid

    def update(
        self,
        table: str,
        data: dict,
        where: str,
        where_params: tuple = (),
    ) -> int:
        """
        Update rows and return affected count.

        Args:
            table: Table name
            data: Dictionary of column -> value
            where: WHERE clause (without WHERE keyword)
            where_params: Parameters for WHERE clause

        Returns:
            Number of affected rows
        """
        set_clause = ", ".join([f"{k} = ?" for k in data.keys()])
        query = f"UPDATE {table} SET {set_clause} WHERE {where}"

        with self.transaction() as conn:
            cursor = conn.execute(query, tuple(data.values()) + where_params)
            return cursor.rowcount

    def delete(
        self,
        table: str,
        where: str,
        where_params: tuple = (),
    ) -> int:
        """
        Delete rows and return affected count.

        Args:
            table: Table name
            where: WHERE clause (without WHERE keyword)
            where_params: Parameters for WHERE clause

        Returns:
            Number of affected rows
        """
        query = f"DELETE FROM {table} WHERE {where}"

        with self.transaction() as conn:
            cursor = conn.execute(query, where_params)
            return cursor.rowcount

    def close(self) -> None:
        """Close database connection."""
        if hasattr(self._local, 'connection') and self._local.connection:
            self._local.connection.close()
            self._local.connection = None

    @staticmethod
    def to_json(obj) -> Optional[str]:
        """Convert object to JSON string for storage."""
        if obj is None:
            return None
        return json.dumps(obj, ensure_ascii=False, default=str)

    @staticmethod
    def from_json(json_str: Optional[str], default=None):
        """Parse JSON string from storage."""
        if json_str is None:
            return default
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            return default


# Singleton instance
_database: Database | None = None


def get_database() -> Database:
    """Get singleton database instance."""
    global _database
    if _database is None:
        _database = Database()
    return _database
