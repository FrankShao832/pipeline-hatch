"""Database connection management for PostgreSQL.

Provides DatabaseManager singleton that handles:
- Engine/pool lifecycle
- Table creation (init_db)
- Session management
- Health checks
- Graceful fallback on connection failure
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from launcher.database.models import Base


def load_db_config() -> dict:
    """Load database configuration from YAML + env var overrides.

    Priority: environment variable > YAML file > hardcoded defaults.
    """
    # Defaults
    config = {
        "host": "localhost",
        "port": 5432,
        "name": "pipeline_db",
        "user": os.environ.get("USER", "pipeline_app"),
        "password": "",
        "pool_size": 5,
        "max_overflow": 10,
        "echo": False,
    }

    # Try to load from YAML
    yaml_path = Path(__file__).parent.parent.parent / "config" / "database.yaml"
    if yaml_path.exists():
        try:
            import yaml
            with open(yaml_path, "r") as f:
                raw = yaml.safe_load(f) or {}
            db_cfg = raw.get("database", {})
            config.update(db_cfg)
        except Exception:
            pass  # Fallback to defaults

    # Environment variable overrides
    env_map = {
        "DB_HOST": "host",
        "DB_PORT": "port",
        "DB_NAME": "name",
        "DB_USER": "user",
        "DB_PASSWORD": "password",
    }
    for env_key, cfg_key in env_map.items():
        val = os.environ.get(env_key)
        if val is not None:
            if cfg_key == "port":
                config[cfg_key] = int(val)
            else:
                config[cfg_key] = val

    return config


def build_db_url(config: dict) -> str:
    """Build PostgreSQL connection URL from config dict."""
    password_part = f":{config['password']}" if config["password"] else ""
    return (
        f"postgresql://{config['user']}{password_part}"
        f"@{config['host']}:{config['port']}/{config['name']}"
    )


class DatabaseManager:
    """Manages PostgreSQL connection lifecycle and session factory."""

    _instance: Optional[DatabaseManager] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, config: Optional[dict] = None):
        # Allow re-init only on first call (singleton)
        if hasattr(self, "_initialized") and self._initialized:
            return

        self.config = config or load_db_config()
        self.db_url = build_db_url(self.config)
        self._engine = None
        self._SessionLocal = None
        self._initialized = False
        self._connected = False

    # -- Connection lifecycle ------------------------------------------------

    def connect(self) -> bool:
        """Establish engine and verify connection.

        Returns:
            True if connection succeeded, False otherwise.
        """
        try:
            self._engine = create_engine(
                self.db_url,
                pool_size=self.config.get("pool_size", 5),
                max_overflow=self.config.get("max_overflow", 10),
                pool_pre_ping=True,
                echo=self.config.get("echo", False),
            )
            self._SessionLocal = sessionmaker(bind=self._engine)
            # Verify connection
            with self._engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            self._connected = True
            self._initialized = True
            return True
        except Exception as exc:
            from launcher.utils.logger import logger
            logger.warning(f"Database connection failed: {exc}")
            self._connected = False
            self._initialized = True
            return False

    def disconnect(self) -> None:
        """Dispose the engine and release connections."""
        if self._engine:
            self._engine.dispose()
            self._engine = None
            self._SessionLocal = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        """Check if the engine is connected and responsive."""
        if not self._engine:
            return False
        try:
            with self._engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    # -- Schema management ---------------------------------------------------

    def init_db(self) -> bool:
        """Create all tables that don't exist yet.

        Returns:
            True if successful, False otherwise.
        """
        if not self._engine:
            return False
        try:
            Base.metadata.create_all(self._engine)
            from launcher.utils.logger import logger
            logger.info("Database tables initialized")
            return True
        except Exception as exc:
            from launcher.utils.logger import logger
            logger.error(f"Failed to initialize database tables: {exc}")
            return False

    def drop_all(self) -> None:
        """Drop all tables. Use with extreme caution (dev only)."""
        if self._engine:
            Base.metadata.drop_all(self._engine)

    # -- Session management --------------------------------------------------

    def get_session(self) -> Session:
        """Get a new SQLAlchemy session.

        Prefer using as context manager:
            with db.get_session() as session:
                session.query(...)
        """
        if not self._SessionLocal:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._SessionLocal()

    def __enter__(self) -> Session:
        """Context manager entry — yields a session."""
        self._context_session = self.get_session()
        return self._context_session

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit — closes session."""
        if hasattr(self, "_context_session"):
            self._context_session.close()
            del self._context_session


# Singleton instance
db_manager = DatabaseManager()
