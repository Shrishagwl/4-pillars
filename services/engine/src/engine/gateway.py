"""Asks telstra-gateway the two questions the engine needs answered.

  - Network Availability: is there a Telstra outage in this suburb right now, and where?
  - Location Verification: is this SIM still at its meter's address? (only for small clusters)

The engine never calls Telstra directly; the gateway handles tokens, headers, retries and
caching. If the gateway can't answer, that signal is left as None ("not known") and the engine
decides without it, the same way the evaluation runs without the API.
"""

import logging
import os
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

import httpx2

from .clues import LOCATION_CHECK_MAX_METERS
from .clustering import Cluster
from .pipeline import Signals

log = logging.getLogger(__name__)

METADATA_URL = (
    "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity"
)

Point = tuple[float, float]  # (lon, lat), the order WKT uses
Polygon = list[list[Point]]  # outer ring first, then holes


class GatewayError(Exception):
    pass


def parse_multipolygon(wkt: str) -> list[Polygon]:
    """MULTIPOLYGON(((lon lat, lon lat, ...)), ((...))) -> polygons of rings of points."""
    if not wkt.strip().upper().startswith("MULTIPOLYGON"):
        raise ValueError("not a MULTIPOLYGON")
    polygons: list[Polygon] = []
    for polygon_text in re.findall(r"\(\((.*?)\)\)", wkt):
        rings = []
        for ring_text in polygon_text.split("),("):
            ring = []
            for pair in ring_text.strip("() ").split(","):
                lon, lat = (float(x) for x in pair.split())
                ring.append((lon, lat))
            rings.append(ring)
        polygons.append(rings)
    return polygons


def _in_ring(point: Point, ring: Sequence[Point]) -> bool:
    """Ray casting: count how many edges a line going east from the point crosses."""
    x, y = point
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, [*ring[1:], ring[0]], strict=True):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def inside(point: Point, polygons: Iterable[Polygon]) -> bool:
    return any(
        _in_ring(point, rings[0]) and not any(_in_ring(point, hole) for hole in rings[1:])
        for rings in polygons
    )


@dataclass(frozen=True, slots=True)
class Place:
    suburb: str
    state: str
    postcode: str


def _cloud_run_token(audience: str) -> dict[str, str]:
    """On Cloud Run the gateway is private, so ask the metadata server for an ID token."""
    if not os.environ.get("K_SERVICE") or not audience.endswith(".run.app"):
        return {}
    res = httpx2.get(
        METADATA_URL, params={"audience": audience}, headers={"Metadata-Flavor": "Google"}
    )
    res.raise_for_status()
    return {"Authorization": f"Bearer {res.text}"}


class Gateway:
    def __init__(
        self,
        base_url: str,
        timeout: float = 5.0,
        transport: httpx2.BaseTransport | None = None,
        auth: Callable[[str], dict[str, str]] = _cloud_run_token,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._auth = auth
        self._client = httpx2.Client(base_url=self._base, timeout=timeout, transport=transport)

    def _headers(self, incident_id: str | None) -> dict[str, str]:
        headers = self._auth(self._base)
        if incident_id:
            headers["x-incident-id"] = incident_id
        return headers

    def current_outages(self, place: Place, incident_id: str | None = None) -> list[dict]:
        try:
            res = self._client.get(
                "/v1/network-availability",
                params={"suburb": place.suburb, "state": place.state, "postcode": place.postcode},
                headers=self._headers(incident_id),
            )
            res.raise_for_status()
        except httpx2.HTTPError as err:
            raise GatewayError(f"network availability for {place.suburb}: {err}") from err
        return list(res.json()["outages"]["current"])

    def verify_location(
        self, msisdn: str, lat: float, lon: float, incident_id: str | None = None
    ) -> str | None:
        """TRUE, FALSE, PARTIAL, or None when the network couldn't locate the SIM."""
        try:
            res = self._client.post(
                "/v1/location-verification",
                json={"msisdn": msisdn, "latitude": lat, "longitude": lon},
                headers=self._headers(incident_id),
            )
            res.raise_for_status()
        except httpx2.HTTPError as err:
            raise GatewayError(f"location verification for {msisdn}: {err}") from err
        return res.json()["verificationResult"]

    def signals(
        self, clusters: Iterable[Cluster], incident_ids: dict[str, str] | None = None
    ) -> Signals:
        """Everything the gateway can tell us about these clusters, as engine Signals.

        `incident_ids` maps cluster_id -> incident id, only used to tag the gateway's logs.
        """
        clusters = list(clusters)
        ids = incident_ids or {}

        # Network Availability, once per place.
        places: dict[Place, str | None] = {}
        for cluster in clusters:
            for m in cluster.members:
                place = Place(m.meter.suburb, m.meter.state, m.meter.postcode)
                places.setdefault(place, ids.get(cluster.cluster_id))
        outage_suburbs: set[str] | None = set()
        areas: list[Polygon] = []
        outages_without_area = 0
        for place, incident_id in places.items():
            if not place.postcode:
                continue
            try:
                current = self.current_outages(place, incident_id)
            except GatewayError:
                log.warning("no outage answer, deciding without it", exc_info=True)
                outage_suburbs = None
                break
            if current:
                outage_suburbs.add(place.suburb)
            for outage in current:
                if not outage.get("affected_area"):
                    outages_without_area += 1
                else:
                    try:
                        areas.extend(parse_multipolygon(outage["affected_area"]))
                    except ValueError:
                        log.warning("unreadable affected_area: %.60s", outage["affected_area"])

        # Which silent SIMs sit inside the outage areas. Only when every current outage came
        # with an area: otherwise SIMs in an outage without one would look unaffected.
        outage_msisdns = None
        if areas and outages_without_area == 0 and outage_suburbs is not None:
            outage_msisdns = {
                m.meter.msisdn
                for cluster in clusters
                for m in cluster.members
                if m.meter.lat is not None
                and m.meter.lon is not None
                and inside((m.meter.lon, m.meter.lat), areas)
            }

        # Location Verification, only for small clusters (one or a few meters: tamper suspects).
        moved: set[str] | None = None
        for cluster in clusters:
            if cluster.size > LOCATION_CHECK_MAX_METERS:
                continue
            for m in cluster.members:
                if m.meter.lat is None or m.meter.lon is None:
                    continue
                try:
                    result = self.verify_location(
                        m.meter.msisdn, m.meter.lat, m.meter.lon, ids.get(cluster.cluster_id)
                    )
                except GatewayError:
                    log.warning("no location answer for %s", m.meter.msisdn, exc_info=True)
                    continue
                moved = moved if moved is not None else set()
                if result == "FALSE":
                    moved.add(m.meter.msisdn)

        return Signals(
            outage_suburbs=outage_suburbs,
            moved_msisdns=moved,
            outage_msisdns=outage_msisdns,
        )

    def close(self) -> None:
        self._client.close()
