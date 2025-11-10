thonimport argparse
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from extractors.zillow_parser import ZillowParser, ZillowClientError
from extractors.utils_geo import compute_centroid
from outputs.exporter_json import export_records
from outputs.exporter_csv import export_to_csv

logger = logging.getLogger("zillow_scraper")

def configure_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

def load_config(config_path: Path) -> Dict[str, Any]:
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with config_path.open("r", encoding="utf-8") as f:
        return json.load(f)

def resolve_path(base_dir: Path, path_str: str) -> Path:
    p = Path(path_str)
    if p.is_absolute():
        return p
    return (base_dir / p).resolve()

def run(config: Dict[str, Any], base_dir: Path) -> None:
    search_cfg = config.get("search", {})
    output_cfg = config.get("output", {})

    cities: List[str] = search_cfg.get("cities", [])
    if not cities:
        logger.warning("No cities defined in configuration. Nothing to do.")
        return

    listing_types: List[str] = search_cfg.get("listingTypes", ["for_rent"])
    home_types: List[str] = search_cfg.get("homeTypes", [])
    max_pages: int = int(search_cfg.get("maxPages", 1))
    language: str = search_cfg.get("language", "en-US")

    output_format: str = output_cfg.get("format", "json").lower()
    output_path_str: str = output_cfg.get("path", "data/output.sample.json")
    output_path = resolve_path(base_dir, output_path_str)

    parser = ZillowParser()
    all_records: List[Dict[str, Any]] = []

    logger.info(
        "Starting Zillow scraping for %d city(ies), listing types=%s, pages per city=%d",
        len(cities),
        ",".join(listing_types),
        max_pages,
    )

    for city in cities:
        for listing_type in listing_types:
            for page in range(1, max_pages + 1):
                try:
                    logger.info(
                        "Fetching city='%s', listingType='%s', page=%d",
                        city,
                        listing_type,
                        page,
                    )
                    records = parser.fetch_city_listings(
                        city=city,
                        listing_type=listing_type,
                        home_types=home_types,
                        page=page,
                        language=language,
                    )
                    logger.info(
                        "Fetched %d listing(s) for %s [%s] page %d",
                        len(records),
                        city,
                        listing_type,
                        page,
                    )
                    all_records.extend(records)
                except ZillowClientError as exc:
                    logger.error(
                        "Failed to fetch listings for %s [%s] page %d: %s",
                        city,
                        listing_type,
                        page,
                        exc,
                    )

    if not all_records:
        logger.warning("No listings found for any query. Exiting without export.")
        return

    coords = [
        (rec.get("latitude"), rec.get("longitude"))
        for rec in all_records
        if rec.get("latitude") is not None and rec.get("longitude") is not None
    ]
    if coords:
        centroid_lat, centroid_lon = compute_centroid(coords)
        logger.info(
            "Computed geographic centroid from %d coordinates: (lat=%.6f, lon=%.6f)",
            len(coords),
            centroid_lat,
            centroid_lon,
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    metadata = {
        "generatedAt": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "cityCount": len(cities),
        "listingTypes": listing_types,
        "recordCount": len(all_records),
    }

    logger.info("Exporting %d record(s) to %s (%s)", len(all_records), output_path, output_format)

    if output_format == "csv":
        export_to_csv(all_records, output_path)
    else:
        export_records(all_records, output_format, output_path, metadata=metadata)

    logger.info("Export complete.")

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Zillow Search Scraper (All-in-one) - CLI entry point"
    )
    parser.add_argument(
        "--config",
        "-c",
        help="Path to configuration JSON (default: data/input.sample.json)",
        default=None,
    )
    parser.add_argument(
        "--format",
        "-f",
        help="Override output format (json, csv, xml, rss, html)",
        default=None,
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Override output file path",
        default=None,
    )
    parser.add_argument(
        "--verbose",
        "-v",
        help="Enable verbose logging",
        action="store_true",
    )
    return parser.parse_args()

def main() -> None:
    args = parse_args()
    configure_logging(args.verbose)

    base_dir = Path(__file__).resolve().parents[1]

    default_config_path = base_dir / "data" / "input.sample.json"
    config_path = Path(args.config) if args.config else default_config_path

    try:
        config = load_config(config_path)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to load configuration from %s: %s", config_path, exc)
        raise SystemExit(1)

    if args.format:
        config.setdefault("output", {})
        config["output"]["format"] = args.format

    if args.output:
        config.setdefault("output", {})
        config["output"]["path"] = args.output

    try:
        run(config, base_dir)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error during execution: %s", exc)
        raise SystemExit(1)

if __name__ == "__main__":
    main()