"""Configuration and feature flags for the new knowledge source and faculty lookup.

Allows switching the new folder source and faculty lookup feature on/off with a single flag.
When flags are set to False, the system behaves exactly as the original project.
"""
from pathlib import Path

# Feature flags: single switch for each new capability
ENABLE_NEW_KB_SOURCE: bool = True
ENABLE_FACULTY_LOOKUP: bool = True
DEBUG_ROUTING: bool = True

# Paths to external sources (Read-only access, files are never moved or copied)
NEW_KB_FOLDER = Path(r"D:\MINI Project\Knowledge base")
NEW_FACULTY_FOLDER = Path(r"D:\MINI Project\faculty")

# Destination for newly extracted photos (never alters original PDFs)
FACULTY_PHOTOS_NEW_DIR = Path(r"D:\MINI Project\faculty_photos_new")

# ChromaDB collection names (Separate namespaces, mce_docs is untouched)
ORIGINAL_COLLECTION_NAME = "mce_docs"
NEW_KB_COLLECTION_NAME = "kb_new_folder"
FACULTY_PROFILES_COLLECTION_NAME = "faculty_profiles"
