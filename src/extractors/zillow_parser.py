thonimport json
import logging
import re
from dataclasses import dataclass, asdict
from typing import Any, Dict, Iterable, List, Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("zillow_scraper.parser")

class ZillowClientError(RuntimeError):
    """Represents errors encountered while fetching or parsing Zillow data."""

@dataclass
class PropertyListing:
    zpid: Optional[str] = None
    providerListingId: Optional[str] = None
    statusType: Optional[str] = None
    statusText: Optional[str] = None
    imageSource: Optional[str] = None
    detailUrl: Optional[str] = None

    address: Optional[str] = None
    addressStreet: Optional[str] = None
    addressCity: Optional[str] = None
    addressState: Optional[str] = None
    addressZipcode: Optional[str] = None

    latitude: Optional[float] = None
    longitude: Optional[float] = None

    buildingName: Optional[str] = None
    contactPhoneNumber: Optional[str] = None

    minPrice: Optional[str] = None
    maxPrice: Optional[str] = None
    unitTypes: Optional[str] = None
    totalUnits: Optional[int] = None

    photoUrls: Optional[List[str]] = None
    isFeaturedListing: Optional[bool] = None
    badgeText: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["photoUrls"] = self.photoUrls or []
        return data

class ZillowParser:
    """
    A lightweight HTML/JSON parser for Zillow search result pages.

    It relies on the JSON state embedded in the page (e.g. __NEXT_DATA__)
    and extracts the fields described in the project README.
    """

    BASE_URL = "https://www.zillow.com"

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            }
        )

    def build_search_url(
        self,
        city: str,
        listing_type: str,
        page: int,
        language: str = "en-US",
    ) -> str:
        """
        Construct a simple search URL.

        This does not perfectly match Zillow's internal routing, but it is
        sufficiently realistic for demonstration and may work in practice.
        """
        slug_city = city.lower().replace(",", "").replace(" ", "-")
        listing_type = listing_type.lower()

        if listing_type in ("for_rent", "for-rent", "rent"):
            path = f"/homes/for_rent/{slug_city}_rb/"
        elif listing_type in ("for_sale", "for-sale", "sale"):
            path = f"/homes/for_sale/{slug_city}_rb/"
        elif listing_type in ("sold", "recently_sold", "recently-sold"):
            path = f"/homes/recently_sold/{slug_city}_rb/"
        else:
            logger.warning(
                "Unknown listing_type='%s', defaulting to for_rent", listing_type
            )
            path = f"/homes/for_rent/{slug_city}_rb/"

        url = f"{self.BASE_URL}{path}"
        if page > 1:
            url = f"{url}{page}_p/"
        logger.debug("Built search URL: %s", url)
        return url

    def fetch_search_page(self, url: str, language: str = "en-US") -> str:
        try:
            headers = {"Accept-Language": language}
            response = self.session.get(url, headers=headers, timeout=20)
            response.raise_for_status()
            return response.text
        except requests.RequestException as exc:  # noqa: BLE001
            logger.error("HTTP error fetching %s: %s", url, exc)
            raise ZillowClientError(f"Failed to fetch {url}: {exc}") from exc

    def _extract_json_state(self, html: str) -> Optional[Dict[str, Any]]:
        """
        Try to locate Zillow's JSON state (__NEXT_DATA__ or similar) in the HTML.
        """
        soup = BeautifulSoup(html, "lxml")

        # Common pattern: <script id="__NEXT_DATA__" type="application/json">...</script>
        script = soup.find("script", id="__NEXT_DATA__", type="application/json")
        if script and script.string:
            try:
                return json.loads(script.string)
            except json.JSONDecodeError as exc:  # noqa: BLE001
                logger.debug("Failed to decode __NEXT_DATA__: %s", exc)

        # Fallback: search for JSON blob containing "searchResults"
        text = soup.get_text(" ", strip=True)
        match = re.search(r'{"props":\s*{.*"searchResults".*}', text)
        if match:
            candidate = match.group(0)
            # Attempt to balance braces crudely
            brace_count = 0
            end_index = 0
            for i, ch in enumerate(candidate):
                if ch == "{":
                    brace_count += 1
                elif ch == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        end_index = i + 1
                        break
            if end_index:
                try:
                    return json.loads(candidate[:end_index])
                except json.JSONDecodeError as exc:  # noqa: BLE001
                    logger.debug("Fallback JSON decode failed: %s", exc)

        logger.warning("Could not locate JSON state in HTML")
        return None

    def _iter_list_results(self, state: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
        """
        Yield raw listing dictionaries from Zillow's nested state.
        """
        try:
            props = state["props"]["pageProps"]
            search_state = props.get("searchPageState") or props.get("searchState")
            cat1 = search_state["cat1"]
            search_results = cat1["searchResults"]
            list_results: List[Dict[str, Any]] = search_results.get("listResults", [])
            for raw in list_results:
                yield raw
        except (KeyError, TypeError) as exc:
            logger.warning("Unexpected JSON structure while extracting results: %s", exc)
            return

    @staticmethod
    def _format_address(raw: Dict[str, Any]) -> Dict[str, Any]:
        addr = raw.get("address") or {}
        street = addr.get("streetAddress") or raw.get("addressStreet")
        city = addr.get("city") or raw.get("addressCity")
        state = addr.get("state") or raw.get("addressState")
        zipcode = addr.get("zipcode") or raw.get("addressZipcode")

        address_parts = [p for p in [street, city, state, zipcode] if p]
        full_address = ", ".join(address_parts) if address_parts else None

        return {
            "address": full_address,
            "addressStreet": street,
            "addressCity": city,
            "addressState": state,
            "addressZipcode": zipcode,
        }

    @staticmethod
    def _extract_photos(raw: Dict[str, Any]) -> List[str]:
        photos: List[str] = []

        if "photoUrls" in raw and isinstance(raw["photoUrls"], list):
            photos.extend([p for p in raw["photoUrls"] if isinstance(p, str)])

        hdp = raw.get("hdpData", {}).get("homeInfo", {})
        if isinstance(hdp, dict):
            if isinstance(hdp.get("photoUrls"), list):
                photos.extend([p for p in hdp["photoUrls"] if isinstance(p, str)])
            if isinstance(hdp.get("photos"), list):
                for p in hdp["photos"]:
                    url = p.get("url")
                    if isinstance(url, str):
                        photos.append(url)

        img_src = raw.get("imgSrc")
        if isinstance(img_src, str):
            photos.insert(0, img_src)

        seen = set()
        unique = []
        for url in photos:
            if url not in seen:
                seen.add(url)
                unique.append(url)
        return unique

    def parse_search_results(self, html: str) -> List[Dict[str, Any]]:
        state = self._extract_json_state(html)
        if state is None:
            logger.warning("No JSON state found, returning empty result set")
            return []

        results: List[Dict[str, Any]] = []

        for raw in self._iter_list_results(state):
            lat_long = raw.get("latLong") or {}
            hdp = raw.get("hdpData", {}).get("homeInfo", {})

            address_info = self._format_address(raw)

            listing = PropertyListing(
                zpid=str(raw.get("zpid") or hdp.get("zpid") or ""),
                providerListingId=raw.get("providerListingId")
                or hdp.get("providerListingId"),
                statusType=raw.get("statusType") or hdp.get("homeStatus"),
                statusText=raw.get("statusText") or raw.get("statusType"),
                imageSource=raw.get("imgSrc"),
                detailUrl=raw.get("detailUrl")
                or raw.get("detailUrlPath")
                or hdp.get("detailUrl"),
                latitude=lat_long.get("latitude") or hdp.get("latitude"),
                longitude=lat_long.get("longitude") or hdp.get("longitude"),
                buildingName=raw.get("buildingName")
                or hdp.get("buildingName")
                or raw.get("name"),
                contactPhoneNumber=raw.get("contactPhoneNumber"),
                minPrice=raw.get("unformattedPrice")
                or raw.get("price")
                or hdp.get("price"),
                maxPrice=raw.get("priceReduction")
                or raw.get("price")  # best-effort
                or hdp.get("price"),
                unitTypes=raw.get("unitTypes")
                or raw.get("bedsBaths")
                or raw.get("beds"),
                totalUnits=raw.get("totalUnits") or hdp.get("totalUnits"),
                photoUrls=self._extract_photos(raw),
                isFeaturedListing=bool(raw.get("isFeaturedListing")),
                badgeText=raw.get("badgeText")
                or (raw.get("variableData") or {}).get("text"),
            )

            listing.address = address_info["address"]
            listing.addressStreet = address_info["addressStreet"]
            listing.addressCity = address_info["addressCity"]
            listing.addressState = address_info["addressState"]
            listing.addressZipcode = address_info["addressZipcode"]

            results.append(listing.to_dict())

        logger.debug("Parsed %d listing(s) from HTML", len(results))
        return results

    def fetch_city_listings(
        self,
        city: str,
        listing_type: str,
        home_types: Optional[List[str]] = None,
        page: int = 1,
        language: str = "en-US",
    ) -> List[Dict[str, Any]]:
        """
        High-level helper that builds the URL, downloads the page,
        parses the results and applies basic post-filtering.
        """
        url = self.build_search_url(city, listing_type, page, language)
        html = self.fetch_search_page(url, language)
        records = self.parse_search_results(html)

        if not records:
            logger.info("No records parsed for %s [%s] page %d", city, listing_type, page)
            return []

        if home_types:
            normalized = {ht.lower() for ht in home_types}
            filtered: List[Dict[str, Any]] = []
            for r in records:
                unit_types = str(r.get("unitTypes") or "").lower()
                if any(ht in unit_types for ht in normalized):
                    filtered.append(r)
            logger.debug(
                "Filtered %d -> %d listing(s) by home_types=%s",
                len(records),
                len(filtered),
                ",".join(home_types),
            )
            return filtered

        return records