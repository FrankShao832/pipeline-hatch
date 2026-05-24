"""SQLAlchemy models for Pipeline Launcher database.

Covers current needs (users, projects, dcc_overrides) and reserves tables
for future tools (Asset Manager, Publisher, Nuke Material Browser).
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Text, ForeignKey,
    ARRAY, JSON, UniqueConstraint, Index, func
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base for all models."""
    pass


# ---------------------------------------------------------------------------
# Core — Pipeline Launcher (Phase 5)
# ---------------------------------------------------------------------------

class User(Base):
    """System user for permission-based access control.

    Detected automatically via getpass.getuser() at startup.
    No password — relies on OS-level authentication.
    """
    __tablename__ = "users"
    __table_args__ = {"comment": "Pipeline users, detected via OS username"}

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="artist")
    # Roles: admin > pipeline > artist
    is_active: Mapped[Optional[bool]] = mapped_column(Boolean, default=True)
    email: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=func.now())
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<User {self.username} [{self.role}]>"


class Project(Base):
    """Pipeline project with root and publish paths."""
    __tablename__ = "projects"
    __table_args__ = {"comment": "Pipeline projects"}

    id = Column(Integer, primary_key=True)
    name = Column(String(128), unique=True, nullable=False, index=True)
    root_path = Column(String(512), nullable=False)
    publish_root = Column(String(512), nullable=False)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    created_by = Column(String(64), ForeignKey("users.username"), nullable=True)

    # Relationship
    dcc_overrides = relationship("DccOverride", back_populates="project",
                                 cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Project {self.name}>"


class DccOverride(Base):
    """Per-project DCC executable/app overrides."""
    __tablename__ = "dcc_overrides"
    __table_args__ = (
        UniqueConstraint("project_id", "role", name="uq_project_role"),
        {"comment": "Per-project DCC path overrides"},
    )

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"),
                        nullable=False)
    role = Column(String(32), nullable=False)  # maya / houdini / nuke
    executable_override = Column(String(512), nullable=True)
    app_name_override = Column(String(256), nullable=True)
    env_file_override = Column(String(512), nullable=True)

    project = relationship("Project", back_populates="dcc_overrides")

    def __repr__(self) -> str:
        return f"<DccOverride {self.role} for project {self.project_id}>"


# ---------------------------------------------------------------------------
# Reserved — Asset Manager (Future)
# ---------------------------------------------------------------------------

class AssetType(Base):
    """Asset category (model, texture, rig, hda, ...)."""
    __tablename__ = "asset_types"

    id = Column(Integer, primary_key=True)
    name = Column(String(64), unique=True, nullable=False)
    icon = Column(String(64), nullable=True)

    assets = relationship("Asset", back_populates="asset_type")


class Asset(Base):
    """Named asset belonging to a project and type."""
    __tablename__ = "assets"
    __table_args__ = (
        UniqueConstraint("project_id", "asset_type_id", "name",
                         name="uq_project_type_asset"),
        {"comment": "Assets managed by Asset Manager"},
    )

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"),
                        nullable=True)
    asset_type_id = Column(Integer, ForeignKey("asset_types.id"),
                           nullable=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    created_by = Column(String(64), ForeignKey("users.username"), nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    asset_type = relationship("AssetType", back_populates="assets")
    versions = relationship("AssetVersion", back_populates="asset",
                            cascade="all, delete-orphan")


class AssetVersion(Base):
    """Versioned file of an asset."""
    __tablename__ = "asset_versions"
    __table_args__ = (
        UniqueConstraint("asset_id", "version", name="uq_asset_version"),
    )

    id = Column(Integer, primary_key=True)
    asset_id = Column(Integer, ForeignKey("assets.id", ondelete="CASCADE"),
                      nullable=False)
    version = Column(Integer, nullable=False)
    file_path = Column(String(1024), nullable=False)
    thumbnail = Column(String(1024), nullable=True)
    notes = Column(Text, nullable=True)
    created_by = Column(String(64), ForeignKey("users.username"), nullable=True)
    created_at = Column(DateTime, default=func.now())

    asset = relationship("Asset", back_populates="versions")


# ---------------------------------------------------------------------------
# Reserved — Publisher (Future)
# ---------------------------------------------------------------------------

class PublishTask(Base):
    """Publish job tracking for file validation and deployment."""
    __tablename__ = "publish_tasks"
    __table_args__ = (
        Index("idx_publish_status", "status"),
    )

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    source_path = Column(String(1024), nullable=False)
    publish_type = Column(String(64), nullable=True)
    # Types: maya_scene, nuke_script, texture, etc.
    status = Column(String(32), default="pending")
    # Statuses: pending / validating / processing / done / failed
    target_path = Column(String(1024), nullable=True)
    created_at = Column(DateTime, default=func.now())
    completed_at = Column(DateTime, nullable=True)


# ---------------------------------------------------------------------------
# Reserved — Nuke Material Browser (Future)
# ---------------------------------------------------------------------------

class MaterialLibrary(Base):
    """Named library of materials within a project."""
    __tablename__ = "material_libraries"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_project_library"),
    )

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"),
                        nullable=False)
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)

    materials = relationship("Material", back_populates="library",
                             cascade="all, delete-orphan")


class Material(Base):
    """Individual material entry with Nuke script snippet."""
    __tablename__ = "materials"

    id = Column(Integer, primary_key=True)
    library_id = Column(Integer,
                        ForeignKey("material_libraries.id", ondelete="CASCADE"),
                        nullable=False)
    name = Column(String(128), nullable=False)
    file_path = Column(String(1024), nullable=False)
    thumbnail = Column(String(1024), nullable=True)
    nuke_script_snippet = Column(Text, nullable=True)
    tags = Column(ARRAY(String), nullable=True)
    created_by = Column(String(64), ForeignKey("users.username"), nullable=True)
    created_at = Column(DateTime, default=func.now())

    library = relationship("MaterialLibrary", back_populates="materials")
