"""
Import weekly retro data from Excel into ValueHunt DB.

Usage:
    python -m scripts.import_retro              # import latest sheet
    python -m scripts.import_retro --dry-run     # preview only
"""
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))  # project root for src.* imports

if __name__ == '__main__':
    from src.retro_import import import_retro, main as _cli
    sys.exit(_cli())
