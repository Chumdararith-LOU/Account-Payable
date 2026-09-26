#!/usr/bin/env python3
"""
Migration script: JSON files → SQLite database
Run this once to migrate your existing data
"""

from database import init_database, migrate_json_to_db

if __name__ == "__main__":
    print("Initializing database...")
    init_database()
    
    print("\nMigrating existing JSON files...")
    migrate_json_to_db("output/ocr")
    
    print("\n✓ Migration complete!")
    print("  - Old JSON files are preserved in output/ocr/")
    print("  - You can now use database queries for reporting")
    print("  - Duplicate invoice checking is now active")