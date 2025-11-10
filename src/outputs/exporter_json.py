thonimport html
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from xml.etree.ElementTree import Element, SubElement, ElementTree

def _ensure_path(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path

def _serialize_for_json(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    serialized: List[Dict[str, Any]] = []
    for rec in records:
        # Basic sanitization: ensure lists and dicts are JSON-serializable
        serialized.append(rec)
    return serialized

def _export_json(records: Iterable[Dict[str, Any]], output_path: Path, metadata: Dict[str, Any]) -> None:
    obj = {
        "metadata": metadata,
        "results": _serialize_for_json(records),
    }
    _ensure_path(output_path)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def _export_xml(records: Iterable[Dict[str, Any]], output_path: Path, metadata: Dict[str, Any]) -> None:
    root = Element("zillowListings")
    meta_el = SubElement(root, "metadata")
    for key, value in metadata.items():
        m = SubElement(meta_el, key)
        m.text = str(value)

    results_el = SubElement(root, "results")

    for rec in records:
        listing_el = SubElement(results_el, "listing")
        for key, value in rec.items():
            child = SubElement(listing_el, key)
            if isinstance(value, list):
                for item in value:
                    item_el = SubElement(child, "item")
                    item_el.text = "" if item is None else str(item)
            else:
                child.text = "" if value is None else str(value)

    _ensure_path(output_path)
    tree = ElementTree(root)
    tree.write(output_path, encoding="utf-8", xml_declaration=True)

def _export_rss(records: Iterable[Dict[str, Any]], output_path: Path, metadata: Dict[str, Any]) -> None:
    """
    Very small RSS feed exporter. Each listing becomes an <item> entry.
    """
    now_rfc822 = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S +0000")
    title = f"Zillow Listings Export ({metadata.get('recordCount', 0)} results)"
    description = "Zillow search results export."

    items_fragments: List[str] = []

    for rec in records:
        detail_url = html.escape(str(rec.get("detailUrl") or ""))
        status_text = html.escape(str(rec.get("statusText") or rec.get("statusType") or "Listing"))
        address = html.escape(str(rec.get("address") or ""))
        guid = html.escape(str(rec.get("zpid") or detail_url or ""))

        item = f"""
        <item>
          <title>{status_text} - {address}</title>
          <link>{detail_url}</link>
          <guid isPermaLink="false">{guid}</guid>
          <pubDate>{now_rfc822}</pubDate>
          <description><![CDATA[
            Status: {status_text}<br/>
            Address: {address}<br/>
            Price: {html.escape(str(rec.get("minPrice") or ""))}
          ]]></description>
        </item>
        """
        items_fragments.append(item.strip())

    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>{html.escape(title)}</title>
    <description>{html.escape(description)}</description>
    <link>https://www.zillow.com</link>
    <lastBuildDate>{now_rfc822}</lastBuildDate>
    {''.join(items_fragments)}
  </channel>
</rss>
"""

    _ensure_path(output_path)
    with output_path.open("w", encoding="utf-8") as f:
        f.write(rss)

def _export_html(records: Iterable[Dict[str, Any]], output_path: Path, metadata: Dict[str, Any]) -> None:
    """
    Export records as a simple responsive HTML table.
    """
    records_list = list(records)
    headers = [
        "zpid",
        "statusType",
        "statusText",
        "address",
        "minPrice",
        "maxPrice",
        "latitude",
        "longitude",
        "detailUrl",
    ]

    thead_cells = "".join(f"<th>{html.escape(col)}</th>" for col in headers)
    rows_html: List[str] = []
    for rec in records_list:
        cells: List[str] = []
        for col in headers:
            value = rec.get(col)
            if col == "detailUrl" and value:
                cell = f'<td><a href="{html.escape(str(value))}">Link</a></td>'
            else:
                cell = f"<td>{html.escape('' if value is None else str(value))}</td>"
            cells.append(cell)
        rows_html.append(f"<tr>{''.join(cells)}</tr>")

    title = "Zillow Listings Export"
    subtitle = f"{metadata.get('recordCount', len(records_list))} listing(s)"

    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>{html.escape(title)}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    body {{
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      margin: 1.5rem;
      color: #222;
    }}
    h1 {{
      font-size: 1.7rem;
      margin-bottom: 0.25rem;
    }}
    h2 {{
      font-size: 1rem;
      font-weight: 400;
      color: #555;
      margin-top: 0;
    }}
    table {{
      border-collapse: collapse;
      width: 100%;
      margin-top: 1rem;
      font-size: 0.9rem;
    }}
    th, td {{
      border: 1px solid #ddd;
      padding: 0.45rem 0.6rem;
      text-align: left;
    }}
    th {{
      background-color: #f5f5f5;
      font-weight: 600;
    }}
    tr:nth-child(even) td {{
      background-color: #fafafa;
    }}
    a {{
      color: #0066cc;
      text-decoration: none;
    }}
    a:hover {{
      text-decoration: underline;
    }}
  </style>
</head>
<body>
  <h1>{html.escape(title)}</h1>
  <h2>{html.escape(subtitle)}</h2>
  <table>
    <thead>
      <tr>{thead_cells}</tr>
    </thead>
    <tbody>
      {''.join(rows_html)}
    </tbody>
  </table>
</body>
</html>
"""

    _ensure_path(output_path)
    with output_path.open("w", encoding="utf-8") as f:
        f.write(html_doc)

def export_records(
    records: Iterable[Dict[str, Any]],
    fmt: str,
    output_path: Path,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Export listing records to JSON, XML, RSS, or HTML.

    Parameters
    ----------
    records : iterable of dict
        Listing dictionaries.
    fmt : str
        One of: 'json', 'xml', 'rss', 'html'.
    output_path : Path
        Target file path.
    metadata : dict, optional
        Additional context to embed in the export.
    """
    fmt = fmt.lower()
    metadata = metadata or {}
    metadata.setdefault(
        "generatedAt", datetime.utcnow().isoformat(timespec="seconds") + "Z"
    )

    if fmt == "json":
        _export_json(records, output_path, metadata)
    elif fmt == "xml":
        _export_xml(records, output_path, metadata)
    elif fmt == "rss":
        _export_rss(records, output_path, metadata)
    elif fmt == "html":
        _export_html(records, output_path, metadata)
    else:
        raise ValueError(f"Unsupported export format: {fmt}")