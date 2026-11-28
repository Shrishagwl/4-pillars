/**
 * Mock data so the dashboard can be built before the backend is live (task 2).
 *
 * It copies how the digital twin lays out its map (services/twin/src/twin/grid.py):
 * the same box around Coburg, the same four suburbs, about 20 transformers each feeding
 * 50 to 150 meters. Because it uses a fixed seed, you get the exact same meters every
 * time you reload, which makes the screen easy to compare against the Figma design.
 *
 * On top of that it creates four incidents, one for each cause the engine can find.
 */

import type { Cause, Incident, Meter } from '../types.ts';
import { chooseAction } from '../utils/costs.ts';
import { dollars } from '../utils/format.ts';
import { templateSummary } from '../utils/summary.ts';

// ---------- The map, copied from the twin ----------

const NORTH = -37.735;
const SOUTH = -37.775;
const WEST = 144.94;
const EAST = 144.99;

/** 2 x 2 grid of suburbs: rows north to south, columns west to east. [name, postcode] */
const SUBURB_GRID = [
  [
    ['Pascoe Vale South', '3044'],
    ['Coburg', '3058'],
  ],
  [
    ['Brunswick West', '3055'],
    ['Brunswick', '3056'],
  ],
];

const N_TRANSFORMERS = 20;
const METER_SPREAD_M = 300;
const EDGE_MARGIN_M = 400;
const MIN_GAP_M = 600;

const M_PER_DEG_LAT = 111_320;
const M_PER_DEG_LON = M_PER_DEG_LAT * Math.cos((((NORTH + SOUTH) / 2) * Math.PI) / 180);

export const MAP_BOUNDS: [[number, number], [number, number]] = [
  [SOUTH, WEST],
  [NORTH, EAST],
];

// ---------- A random number generator you can repeat ----------

/**
 * Math.random() gives different numbers every reload. This one (called mulberry32) gives the
 * same sequence for the same seed, which is what "seeded" means.
 */
function seededRandom(seed: number): () => number {
  let a = seed;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** A bell-curve random number (mean 0, spread 1), so meters bunch up near their transformer. */
function bellCurve(rand: () => number): number {
  const u = 1 - rand();
  const v = rand();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

function distanceM(aLat: number, aLon: number, bLat: number, bLon: number): number {
  return Math.hypot((aLat - bLat) * M_PER_DEG_LAT, (aLon - bLon) * M_PER_DEG_LON);
}

function suburbOf(lat: number, lon: number): { name: string; postcode: string } {
  const row = lat > (NORTH + SOUTH) / 2 ? 0 : 1; // north half is row 0
  const col = lon < (WEST + EAST) / 2 ? 0 : 1; // west half is column 0
  const [name, postcode] = SUBURB_GRID[row][col];
  return { name, postcode };
}

const pad = (n: number, width: number) => String(n).padStart(width, '0');

// ---------- Build the meters ----------

interface Transformer {
  id: string;
  lat: number;
  lon: number;
}

function buildMeters(rand: () => number): Meter[] {
  const marginLat = EDGE_MARGIN_M / M_PER_DEG_LAT;
  const marginLon = EDGE_MARGIN_M / M_PER_DEG_LON;

  // Place transformers anywhere in the box, but not too close to each other.
  const transformers: Transformer[] = [];
  while (transformers.length < N_TRANSFORMERS) {
    const lat = SOUTH + marginLat + rand() * (NORTH - SOUTH - 2 * marginLat);
    const lon = WEST + marginLon + rand() * (EAST - WEST - 2 * marginLon);
    const tooClose = transformers.some((t) => distanceM(lat, lon, t.lat, t.lon) < MIN_GAP_M);
    if (!tooClose) {
      transformers.push({ id: `T-${pad(transformers.length + 1, 2)}`, lat, lon });
    }
  }

  // Scatter 50 to 150 meters around each transformer.
  const meters: Meter[] = [];
  for (const t of transformers) {
    const howMany = 50 + Math.floor(rand() * 101);
    for (let i = 0; i < howMany; i++) {
      let lat: number;
      let lon: number;
      do {
        lat = t.lat + (bellCurve(rand) * METER_SPREAD_M) / M_PER_DEG_LAT;
        lon = t.lon + (bellCurve(rand) * METER_SPREAD_M) / M_PER_DEG_LON;
      } while (lat > NORTH || lat < SOUTH || lon < WEST || lon > EAST);
      const n = meters.length + 1;
      const { name, postcode } = suburbOf(lat, lon);
      meters.push({
        meterId: `M-${pad(n, 4)}`,
        msisdn: `61412${pad(n, 6)}`,
        transformerId: t.id,
        suburb: name,
        postcode,
        lat,
        lon,
      });
    }
  }
  return meters;
}

// ---------- Build the incidents ----------

/** Evidence lines in the same format as the engine's build_evidence() in evidence.py. */
function names(items: string[]): string {
  const shown = items.slice(0, 3).join(', ');
  return items.length > 3 ? `${shown} and ${items.length - 3} more` : shown;
}

function hhmmss(ms: number): string {
  return new Date(ms).toLocaleTimeString('en-AU', { hour12: false });
}

/** The average position of a group of meters. */
function centreOf(group: Meter[]): [number, number] {
  const lat = group.reduce((sum, m) => sum + m.lat, 0) / group.length;
  const lon = group.reduce((sum, m) => sum + m.lon, 0) / group.length;
  return [lat, lon];
}

/** How far the middle of a group of meters is from a point, in metres. */
function distanceFrom(point: [number, number], group: Meter[]): number {
  const [lat, lon] = centreOf(group);
  return distanceM(point[0], point[1], lat, lon);
}

function mostCommon(values: string[]): string {
  const counts = new Map<string, number>();
  for (const v of values) counts.set(v, (counts.get(v) ?? 0) + 1);
  return [...counts.entries()].sort((a, b) => b[1] - a[1])[0][0];
}

interface IncidentRecipe {
  id: string;
  meters: Meter[];
  probabilities: Record<Cause, number>;
  minutesAgo: number;
  secondsToVerdict: number;
  spreadSeconds: number;
  burstShare: number;
  reasonCodes: string;
  outageApi: string;
  locationCheck?: string;
  rule: string;
}

function makeIncident(recipe: IncidentRecipe, allMeters: Meter[], now: number): Incident {
  const { meters, probabilities } = recipe;
  const transformerIds = [...new Set(meters.map((m) => m.transformerId))].sort();
  const onThoseTransformers = allMeters.filter((m) => transformerIds.includes(m.transformerId));
  const suburb = mostCommon(meters.map((m) => m.suburb));
  const postcode = meters.find((m) => m.suburb === suburb)?.postcode ?? '';

  const cause = (Object.keys(probabilities) as Cause[]).reduce((a, b) =>
    probabilities[a] >= probabilities[b] ? a : b,
  );
  const confidence = probabilities[cause];
  const choice = chooseAction(probabilities, meters.length);

  const openedAt = now - recipe.minutesAgo * 60_000;
  const updatedAt = openedAt + recipe.secondsToVerdict * 1000;
  const share = Math.round((meters.length / onThoseTransformers.length) * 100);
  const confidenceText = `${Math.round(confidence * 100)}%`;

  const actionReason =
    choice.action === 'MANUAL_REVIEW'
      ? `only ${confidenceText} sure it is ${cause}, below the 60% needed to act without a person`
      : `cheapest expected cost: ${dollars(choice.cost)} against ${dollars(choice.runnerUpCost)} for ${choice.runnerUp}`;

  const evidence = [
    `Meters: ${meters.length} silent (${names(meters.map((m) => m.meterId))})`,
    `Where: transformer(s) ${names(transformerIds)} in ${suburb}; ${share}% of the meters on them are silent`,
    `Timing: first drop ${hhmmss(openedAt)}, last ${hhmmss(openedAt + recipe.spreadSeconds * 1000)} (${recipe.spreadSeconds} s apart); ${Math.round(recipe.burstShare * 100)}% dropped within 30 s of each other`,
    `Reason codes: ${recipe.reasonCodes}`,
    `Outage API: ${recipe.outageApi}`,
    ...(recipe.locationCheck ? [`Location Verification: ${recipe.locationCheck}`] : []),
    `Verdict: ${cause} at ${confidenceText} (rule '${recipe.rule}')`,
    `Action: ${choice.action} (${actionReason})`,
  ];

  return {
    incidentId: recipe.id,
    meterCount: meters.length,
    probabilities,
    cause,
    confidence,
    action: choice.action,
    evidence,
    updatedAt: new Date(updatedAt).toISOString(),
    ...templateSummary({ meterCount: meters.length, cause, confidence, action: choice.action }),
    suburb,
    postcode,
    transformerIds,
    meterIds: meters.map((m) => m.meterId),
    openedAt: new Date(openedAt).toISOString(),
  };
}

// ---------- Put it all together ----------

export interface DashboardData {
  meters: Meter[];
  incidents: Incident[];
}

export function createMockData(seed = 42, now = Date.now()): DashboardData {
  const rand = seededRandom(seed);
  const meters = buildMeters(rand);
  const used = new Set<string>(); // meters already in an incident
  const suburbs = [...new Set(meters.map((m) => m.suburb))];
  const inSuburb = (suburb: string) => meters.filter((m) => m.suburb === suburb);

  // 1. Network outage: about 70% of the biggest suburb, across many transformers.
  const networkSuburb = [...suburbs].sort((a, b) => inSuburb(b).length - inSuburb(a).length)[0];
  const networkMeters = inSuburb(networkSuburb).filter(() => rand() < 0.7);
  for (const m of networkMeters) used.add(m.meterId);
  const networkCentre = centreOf(networkMeters);

  // 2. Power outage: every meter on one transformer goes quiet. We pick a big transformer
  //    far from the network outage, so the two don't sit on top of each other on the map.
  const transformerIds = [...new Set(meters.map((m) => m.transformerId))];
  const powerTransformer = transformerIds
    .map((id) => meters.filter((m) => m.transformerId === id && !used.has(m.meterId)))
    .filter((group) => group.length >= 80)
    .sort((a, b) => distanceFrom(networkCentre, b) - distanceFrom(networkCentre, a))[0];
  const powerMeters = powerTransformer ?? [];
  for (const m of powerMeters) used.add(m.meterId);
  const powerSuburb = mostCommon(powerMeters.map((m) => m.suburb));

  // 3 and 4. One faulty meter and one tampered meter, near the middle of the other suburbs.
  const [faultSuburb, tamperSuburb] = suburbs.filter(
    (s) => s !== powerSuburb && s !== networkSuburb,
  );
  const pickOne = (suburb: string) => {
    const free = inSuburb(suburb).filter((m) => !used.has(m.meterId));
    const centre = centreOf(free);
    const meter = free.sort((a, b) => distanceFrom(centre, [a]) - distanceFrom(centre, [b]))[0];
    used.add(meter.meterId);
    return meter;
  };
  const faultMeter = pickOne(faultSuburb ?? powerSuburb);
  const tamperMeter = pickOne(tamperSuburb ?? networkSuburb);

  const incidents = [
    makeIncident(
      {
        id: 'INC-0142',
        meters: powerMeters,
        probabilities: { POWER: 0.92, NETWORK: 0.05, METER_FAULT: 0.02, TAMPER: 0.01 },
        minutesAgo: 3,
        secondsToVerdict: 160,
        spreadSeconds: 8,
        burstShare: 0.96,
        reasonCodes: '71% detached (includes last gasp), 29% detection timeout',
        outageApi: 'no outage listed for these meters',
        rule: 'whole transformer went quiet within seconds, most with a last gasp',
      },
      meters,
      now,
    ),
    makeIncident(
      {
        id: 'INC-0141',
        meters: networkMeters,
        probabilities: { NETWORK: 0.9, POWER: 0.06, METER_FAULT: 0.02, TAMPER: 0.02 },
        minutesAgo: 9,
        secondsToVerdict: 140,
        spreadSeconds: 172,
        burstShare: 0.18,
        reasonCodes: '100% detection timeout',
        outageApi: 'outage listed, covering 100% of the cluster',
        rule: 'spread across many transformers in one suburb, and Telstra lists an outage there',
      },
      meters,
      now,
    ),
    makeIncident(
      {
        id: 'INC-0139',
        meters: [faultMeter],
        probabilities: { METER_FAULT: 0.74, NETWORK: 0.12, POWER: 0.08, TAMPER: 0.06 },
        minutesAgo: 22,
        secondsToVerdict: 185,
        spreadSeconds: 0,
        burstShare: 1,
        reasonCodes: '100% detection timeout',
        outageApi: 'no outage listed for these meters',
        rule: 'a single meter went quiet while its neighbours kept reporting',
      },
      meters,
      now,
    ),
    makeIncident(
      {
        id: 'INC-0138',
        meters: [tamperMeter],
        probabilities: { TAMPER: 0.58, METER_FAULT: 0.34, POWER: 0.05, NETWORK: 0.03 },
        minutesAgo: 31,
        secondsToVerdict: 240,
        spreadSeconds: 0,
        burstShare: 1,
        reasonCodes: '100% detached (includes last gasp)',
        outageApi: 'no outage listed for these meters',
        locationCheck: '100% of SIMs have moved',
        rule: 'one meter went quiet and its SIM came back somewhere else',
      },
      meters,
      now,
    ),
  ];

  return { meters, incidents };
}
