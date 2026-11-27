/**
 * The map of meters and incidents (task 5).
 *
 * Leaflet does the map. react-leaflet lets us describe the map with JSX like any other
 * component. `preferCanvas` draws the dots on one canvas instead of 2,000 separate SVG
 * elements, which is what keeps it smooth.
 */
import L from 'leaflet';
import { useMemo } from 'react';
import { Circle, CircleMarker, MapContainer, Marker, TileLayer } from 'react-leaflet';
import { MAP_BOUNDS } from '../data/mockData.ts';
import type { Incident, Meter } from '../types.ts';
import { CAUSE_STYLE, ONLINE_COLOR } from '../utils/causes.ts';

interface Props {
  meters: Meter[];
  incidents: Incident[];
  selectedId?: string;
  onSelect?: (incidentId: string) => void;
  /** When set, the map zooms to this one incident and cannot be dragged (the mini map). */
  focusId?: string;
}

interface Cluster {
  incident: Incident;
  center: [number, number];
  radiusM: number;
}

const TILES = 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png';
const ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>';

export function MeterMap({ meters, incidents, selectedId, onSelect, focusId }: Props) {
  // useMemo means "only redo this work when meters or incidents change", not on every render.
  const { incidentOf, clusters } = useMemo(
    () => buildClusters(meters, incidents),
    [meters, incidents],
  );

  const focus = clusters.find((c) => c.incident.incidentId === focusId);
  const bounds = focus ? boundsAround(focus) : MAP_BOUNDS;
  const isMini = focus !== undefined;

  return (
    <MapContainer
      className="meter-map"
      bounds={bounds}
      boundsOptions={{ padding: isMini ? [24, 24] : [8, 8] }}
      preferCanvas
      zoomSnap={0.25}
      zoomControl={!isMini}
      dragging={!isMini}
      scrollWheelZoom={!isMini}
      doubleClickZoom={!isMini}
      touchZoom={!isMini}
      keyboard={!isMini}
    >
      <TileLayer url={TILES} attribution={ATTRIBUTION} />

      {/* Incident areas first, so the meter dots are drawn on top of them. */}
      {clusters.map(({ incident, center, radiusM }) => {
        const color = CAUSE_STYLE[incident.cause].color;
        const selected = incident.incidentId === selectedId;
        return (
          <Circle
            key={incident.incidentId}
            center={center}
            radius={radiusM}
            pathOptions={{
              color,
              weight: selected ? 3 : 1.5,
              opacity: selected ? 1 : 0.7,
              fillColor: color,
              fillOpacity: selected ? 0.18 : 0.1,
              dashArray: incident.cause === 'NETWORK' ? '6 6' : undefined,
            }}
            eventHandlers={{ click: () => onSelect?.(incident.incidentId) }}
          />
        );
      })}

      {meters.map((meter) => {
        const incident = incidentOf.get(meter.meterId);
        return (
          <CircleMarker
            key={meter.meterId}
            center={[meter.lat, meter.lon]}
            radius={incident ? 3 : 2}
            interactive={false}
            pathOptions={{
              stroke: false,
              fillColor: incident ? CAUSE_STYLE[incident.cause].color : ONLINE_COLOR,
              fillOpacity: incident ? 0.95 : 0.55,
            }}
          />
        );
      })}

      {/* The white label above each incident, e.g. "Coburg · 113". Hidden on the mini map. */}
      {!isMini &&
        clusters.map((cluster) => (
          <Marker
            key={`label-${cluster.incident.incidentId}`}
            position={labelPosition(cluster)}
            icon={labelIcon(cluster.incident, cluster.incident.incidentId === selectedId)}
            eventHandlers={{ click: () => onSelect?.(cluster.incident.incidentId) }}
          />
        ))}
    </MapContainer>
  );
}

// ---------- Helpers (plain functions, no React) ----------

const M_PER_DEG_LAT = 111_320;

function buildClusters(meters: Meter[], incidents: Incident[]) {
  const byId = new Map(meters.map((m) => [m.meterId, m]));
  const incidentOf = new Map<string, Incident>();
  const clusters: Cluster[] = [];

  for (const incident of incidents) {
    const members = incident.meterIds.map((id) => byId.get(id)).filter((m) => m !== undefined);
    if (members.length === 0) continue;
    for (const m of members) incidentOf.set(m.meterId, incident);

    // Centre = the average position. Radius = big enough to hold 85% of the meters, so a few
    // stray meters far away don't blow the circle up to cover the whole map.
    const lat = members.reduce((sum, m) => sum + m.lat, 0) / members.length;
    const lon = members.reduce((sum, m) => sum + m.lon, 0) / members.length;
    const mPerDegLon = M_PER_DEG_LAT * Math.cos((lat * Math.PI) / 180);
    const distances = members
      .map((m) => Math.hypot((m.lat - lat) * M_PER_DEG_LAT, (m.lon - lon) * mPerDegLon))
      .sort((a, b) => a - b);
    const reach = distances[Math.floor((distances.length - 1) * 0.85)];
    clusters.push({ incident, center: [lat, lon], radiusM: Math.max(reach + 60, 120) });
  }
  return { incidentOf, clusters };
}

function labelPosition({ center, radiusM }: Cluster): [number, number] {
  return [center[0] + radiusM / M_PER_DEG_LAT, center[1]]; // top edge of the circle
}

function boundsAround({ center, radiusM }: Cluster): [[number, number], [number, number]] {
  const dLat = (radiusM * 1.4) / M_PER_DEG_LAT;
  const dLon = (radiusM * 1.4) / (M_PER_DEG_LAT * Math.cos((center[0] * Math.PI) / 180));
  return [
    [center[0] - dLat, center[1] - dLon],
    [center[0] + dLat, center[1] + dLon],
  ];
}

/** Leaflet markers take HTML strings, so we escape the text to be safe with live data. */
function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
}

function labelIcon(incident: Incident, selected: boolean): L.DivIcon {
  const color = CAUSE_STYLE[incident.cause].color;
  const text = `${escapeHtml(incident.suburb)} · ${incident.meterCount}`;
  return L.divIcon({
    className: 'map-label-anchor',
    iconSize: [0, 0],
    html: `<span class="map-label${selected ? ' map-label--selected' : ''}"><i style="background:${color}"></i>${text}</span>`,
  });
}
