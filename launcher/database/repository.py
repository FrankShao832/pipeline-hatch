"""Data access layer (Repository pattern) for Pipeline Launcher.

Provides typed CRUD operations for User and Project entities,
abstracting away SQLAlchemy session management.

Uses SQLAlchemy 2.0 ``select()`` style for type-checker compatibility.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from launcher.database.models import User, Project, DccOverride


# ---------------------------------------------------------------------------
# Base Repository
# ---------------------------------------------------------------------------

class BaseRepository:
    """Generic base class providing session access."""

    def __init__(self, session: Session):
        self.session = session


# ---------------------------------------------------------------------------
# User Repository
# ---------------------------------------------------------------------------

class UserRepo(BaseRepository):
    """CRUD operations for users."""

    def get_by_username(self, username: str) -> Optional[User]:
        """Lookup user by system username.

        Args:
            username: OS username (from getpass.getuser()).

        Returns:
            User object or None if not found.
        """
        return self.session.execute(
            select(User).where(User.username == username)
        ).scalar_one_or_none()

    def get_or_create(self, username: str, **defaults) -> User:
        """Find existing user or create a new one.

        Args:
            username: OS username.
            **defaults: Fields to set on creation (display_name, role, etc.).

        Returns:
            Existing or newly created User.
        """
        user = self.get_by_username(username)
        if user is None:
            user = User(username=username, **defaults)
            self.session.add(user)
            self.session.commit()
            self.session.refresh(user)
        return user

    def list_users(self) -> list[User]:
        """Get all users ordered by creation date."""
        return list(
            self.session.execute(
                select(User).order_by(User.created_at.desc())
            ).scalars().all()
        )

    def update_role(self, user_id: int, role: str) -> Optional[User]:
        """Change a user's role.

        Args:
            user_id: Target user ID.
            role: New role (admin / pipeline / artist).

        Returns:
            Updated User or None if not found.
        """
        user = self.session.get(User, user_id)
        if user:
            user.role = role
            self.session.commit()
            self.session.refresh(user)
        return user

    def update_last_login(self, username: str) -> None:
        """Update the last_login timestamp for a user.

        Args:
            username: OS username.
        """
        user = self.get_by_username(username)
        if user:
            user.last_login = datetime.now()
            self.session.commit()

    def set_active(self, user_id: int, is_active: bool) -> Optional[User]:
        """Enable or disable a user account.

        Args:
            user_id: Target user ID.
            is_active: True to enable, False to disable.

        Returns:
            Updated User or None if not found.
        """
        user = self.session.get(User, user_id)
        if user:
            user.is_active = is_active
            self.session.commit()
            self.session.refresh(user)
        return user

    def delete_user(self, user_id: int) -> bool:
        """Delete a user by ID.

        Args:
            user_id: Target user ID.

        Returns:
            True if deleted, False if not found.
        """
        user = self.session.get(User, user_id)
        if user:
            self.session.delete(user)
            self.session.commit()
            return True
        return False

    @property
    def is_empty(self) -> bool:
        """Check if the users table has any records.

        Used to detect first-run (no users = need admin setup).
        """
        return self.session.execute(
            select(func.count()).select_from(User)
        ).scalar_one() == 0


# ---------------------------------------------------------------------------
# Project Repository
# ---------------------------------------------------------------------------

class ProjectRepo(BaseRepository):
    """CRUD operations for projects."""

    def list_projects(self) -> list[Project]:
        """Get all projects ordered by name."""
        return list(
            self.session.execute(
                select(Project).order_by(Project.name.asc())
            ).scalars().all()
        )

    def list_enabled(self) -> list[Project]:
        """Get only enabled projects."""
        return list(
            self.session.execute(
                select(Project)
                .where(Project.enabled.is_(True))
                .order_by(Project.name.asc())
            ).scalars().all()
        )

    def get_by_name(self, name: str) -> Optional[Project]:
        """Find project by name.

        Args:
            name: Project name (unique).

        Returns:
            Project or None.
        """
        return self.session.execute(
            select(Project).where(Project.name == name)
        ).scalar_one_or_none()

    def get_by_id(self, project_id: int) -> Optional[Project]:
        """Find project by ID.

        Args:
            project_id: Project primary key.

        Returns:
            Project or None.
        """
        return self.session.get(Project, project_id)

    def create(self, name: str, root_path: str, publish_root: str,
               created_by: Optional[str] = None,
               enabled: bool = True) -> Project:
        """Create a new project.

        Args:
            name: Unique project name.
            root_path: Project root directory path.
            publish_root: Publish output directory path.
            created_by: Username of the creator.
            enabled: Whether the project is active.

        Returns:
            Newly created Project.
        """
        project = Project(
            name=name,
            root_path=root_path,
            publish_root=publish_root,
            created_by=created_by,
            enabled=enabled,
        )
        self.session.add(project)
        self.session.commit()
        self.session.refresh(project)
        return project

    def update(self, project_id: int, **kwargs) -> Optional[Project]:
        """Update fields on an existing project.

        Allowed kwargs: name, root_path, publish_root, enabled.

        Args:
            project_id: Target project ID.
            **kwargs: Fields to update.

        Returns:
            Updated Project or None if not found.
        """
        allowed = {"name", "root_path", "publish_root", "enabled"}
        project = self.session.get(Project, project_id)
        if project:
            for key, value in kwargs.items():
                if key in allowed:
                    setattr(project, key, value)
            self.session.commit()
            self.session.refresh(project)
        return project

    def delete(self, project_id: int) -> bool:
        """Delete a project by ID.

        Cascades to dcc_overrides.

        Args:
            project_id: Target project ID.

        Returns:
            True if deleted, False if not found.
        """
        project = self.session.get(Project, project_id)
        if project:
            self.session.delete(project)
            self.session.commit()
            return True
        return False

    def count(self) -> int:
        """Get total number of projects."""
        return self.session.execute(
            select(func.count()).select_from(Project)
        ).scalar_one()


# ---------------------------------------------------------------------------
# DCC Override Repository (lightweight, for future use)
# ---------------------------------------------------------------------------

class DccOverrideRepo(BaseRepository):
    """CRUD operations for per-project DCC overrides."""

    def get_for_project(self, project_id: int) -> list[DccOverride]:
        """Get all overrides for a project."""
        return list(
            self.session.execute(
                select(DccOverride)
                .where(DccOverride.project_id == project_id)
            ).scalars().all()
        )

    def get(self, project_id: int, role: str) -> Optional[DccOverride]:
        """Get override for a specific project + role combination."""
        return self.session.execute(
            select(DccOverride).where(
                DccOverride.project_id == project_id,
                DccOverride.role == role,
            )
        ).scalar_one_or_none()

    def upsert(self, project_id: int, role: str, **overrides) -> DccOverride:
        """Create or update a DCC override for a project.

        Args:
            project_id: Target project.
            role: DCC role (maya/houdini/nuke).
            **overrides: executable_override, app_name_override, etc.

        Returns:
            Created or updated DccOverride.
        """
        override = self.get(project_id, role)
        if override is None:
            override = DccOverride(project_id=project_id, role=role, **overrides)
            self.session.add(override)
        else:
            for key, value in overrides.items():
                if hasattr(override, key):
                    setattr(override, key, value)
        self.session.commit()
        self.session.refresh(override)
        return override

    def delete(self, project_id: int, role: str) -> bool:
        """Delete an override for a project + role."""
        override = self.get(project_id, role)
        if override:
            self.session.delete(override)
            self.session.commit()
            return True
        return False
