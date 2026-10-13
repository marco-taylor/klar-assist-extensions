"""Support memory-only runner and ordinary local unittest discovery."""
try:
    from isolated_files import files
except ModuleNotFoundError:
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    files = {str(path.relative_to(root)): path.read_bytes()
             for path in root.rglob('*') if path.is_file()
             and ('__pycache__' not in path.parts)}
