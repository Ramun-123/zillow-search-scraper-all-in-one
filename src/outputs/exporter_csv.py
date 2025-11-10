thonimport csv
from pathlib import Path
from typing import Any, Dict, Iterable, List

def _ensure_path(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path

def _collect_fieldnames(records: Iterable[Dict[str, Any]]) -> List[str]:
    fieldnames: List[str] = []
    seen = set()
    for rec in records:
        for key in rec.keys():
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)
    return fieldnames

def export_to_csv(records: Iterable[Dict[str, Any]], output_path: Path) -> None:
    """
    Export listing dictionaries as a flat CSV file.

    List-valued fields such as photoUrls are joined with a pipe ("|").
    """
    records_list = list(records)
    if not records_list:
        _ensure_path(output_path)
        # write empty file
        with output_path.open("w", encoding="utf-8", newline="") as f:
            f.write("")
        return

    fieldnames = _collect_fieldnames(records_list)
    _ensure_path(output_path)

    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for rec in records_list:
            flat: Dict[str, Any] = {}
            for key, value in rec.items():
                if isinstance(value, list):
                    flat[key] = "|".join("" if v is None else str(v) for v in value)
                else:
                    flat[key] = "" if value is None else value
            writer.writerow(flat)