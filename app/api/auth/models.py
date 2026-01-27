"""
Auth models.
Owns: User data structures.
"""

from pydantic import BaseModel
from uuid import UUID


class AuthenticatedUser(BaseModel):
    id: UUID
    email: str | None = None
    exp: int
