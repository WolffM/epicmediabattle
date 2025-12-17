"""
Pydantic models for the Arena API.
"""

from typing import List, Optional

from pydantic import BaseModel


class BattleResult(BaseModel):
    """Request body for logging a battle result."""
    winner_path: str
    loser_path: str
    scope_level: str
    scope_universe: Optional[str] = None
    scope_ip: str
    scope_group: Optional[str] = None
    scope_character: Optional[str] = None
    scope_source: Optional[str] = None
    scope_variant: Optional[str] = None
    match_source: bool = False
    match_variant: bool = False
    match_variant_group: bool = False
    exclude_recent: List[str] = []  # Recent images to exclude from next matchup


class MatchupRequest(BaseModel):
    """Request for getting a new matchup."""
    scope_level: str
    scope_universe: Optional[str] = None
    scope_ip: str
    scope_group: Optional[str] = None
    scope_character: Optional[str] = None
    scope_source: Optional[str] = None
    scope_variant: Optional[str] = None
    match_source: bool = False
    match_variant: bool = False
    match_variant_group: bool = False


class UndoRequest(BaseModel):
    """Request for undoing a battle."""
    battle_id: str


class DeleteRequest(BaseModel):
    """Request for deleting an image (no contest)."""
    delete_path: str
    keep_path: str
    scope_level: str
    scope_universe: Optional[str] = None
    scope_ip: str
    scope_group: Optional[str] = None
    scope_character: Optional[str] = None
    scope_source: Optional[str] = None
    scope_variant: Optional[str] = None
    match_source: bool = False
    match_variant: bool = False
    match_variant_group: bool = False
    exclude_recent: List[str] = []  # Recent images to exclude from next matchup


class BulkDeleteRequest(BaseModel):
    """Request for bulk deleting images."""
    paths: List[str]


class MergeRequest(BaseModel):
    """Request for merging duplicate images."""
    paths: List[str]
