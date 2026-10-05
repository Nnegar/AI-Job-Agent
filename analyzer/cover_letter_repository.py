"""Backward-compatibility module for cover letter repository."""
from database.cover_letter_repository import (
    CoverLetterRepository,
    save_cover_letter,
)

__all__ = ["CoverLetterRepository", "save_cover_letter"]
