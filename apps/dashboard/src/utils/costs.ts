/**
 * The cost model, copied from the engine (services/engine/src/engine/decision.py) so the
 * dashboard can explain the engine's choice in dollars.
 *
 * Values from task 3 ("Set the cost of each decision"). Sources and working for every number
 * are in docs/decision-costs.md. If you change one here, change it in the engine too.
 */
import type { Action, Cause, Incident } from '../types.ts';

export const COSTS = {
  truckRoll: 650, // one technician visit (Jemena wasted site attendance fee, business hours)
  powerCrew: 1200, // one power crew call-out (2 workers x 2 hours)
  latePowerPerMeter: 28, // a power cut we did not act on, per customer (AER value of reliability)
  meterLeftBroken: 125, // a faulty meter left alone: two manual reads until it is fixed
  missedTamper: 600, // tampering not investigated: about six months of stolen power
  manualReview: 20, // ten minutes of an operator
  reviewDelayShare: 0.1, // a review delays the real fix by this share of doing nothing
};

export const MIN_CONFIDENCE = 0.6;

/** The right thing to do for each true cause. */
export const RIGHT_ACTION: Record<Cause, Action> = {
  POWER: 'DISPATCH_POWER_CREW',
  NETWORK: 'WAIT_FOR_NETWORK',
  METER_FAULT: 'DISPATCH_METER_TECH',
  TAMPER: 'INVESTIGATE_TAMPER',
};

const REAL_ACTIONS: Action[] = Object.values(RIGHT_ACTION);

/** What it costs to send someone, whether or not they were needed. */
function visit(action: Action): number {
  if (action === 'DISPATCH_POWER_CREW') return COSTS.powerCrew;
  if (action === 'DISPATCH_METER_TECH' || action === 'INVESTIGATE_TAMPER') return COSTS.truckRoll;
  return 0;
}

/** What it costs to leave this cause unhandled. */
function missed(cause: Cause, meters: number): number {
  if (cause === 'POWER') return COSTS.latePowerPerMeter * meters;
  if (cause === 'METER_FAULT') return COSTS.meterLeftBroken;
  if (cause === 'TAMPER') return COSTS.missedTamper;
  return 0; // a network outage fixes itself
}

/** Extra dollars spent by taking `action` when the true cause is `cause`. */
function avoidableCost(action: Action, cause: Cause, meters: number): number {
  if (action === 'MANUAL_REVIEW') {
    return COSTS.manualReview + COSTS.reviewDelayShare * missed(cause, meters);
  }
  if (action === RIGHT_ACTION[cause]) return 0;
  const onSite: Action[] = ['DISPATCH_METER_TECH', 'INVESTIGATE_TAMPER'];
  if (onSite.includes(action) && onSite.includes(RIGHT_ACTION[cause])) {
    return COSTS.truckRoll / 2; // right place, wrong person
  }
  return visit(action) + missed(cause, meters);
}

/** Average cost of an action, weighted by how likely each cause is. */
export function expectedCost(
  action: Action,
  probabilities: Record<string, number>,
  meters: number,
): number {
  let total = 0;
  for (const [cause, p] of Object.entries(probabilities)) {
    total += p * avoidableCost(action, cause as Cause, meters);
  }
  return total;
}

export interface Choice {
  action: Action;
  cost: number;
  runnerUp: Action;
  runnerUpCost: number;
}

/** Same rule as the engine: cheapest expected cost, or a person if under 60% sure. */
export function chooseAction(probabilities: Record<string, number>, meters: number): Choice {
  const ranked = REAL_ACTIONS.map((action) => ({
    action,
    cost: expectedCost(action, probabilities, meters),
  })).sort((a, b) => a.cost - b.cost);
  const confidence = Math.max(...Object.values(probabilities));
  const best = confidence < MIN_CONFIDENCE ? 'MANUAL_REVIEW' : ranked[0].action;
  const runnerUp = ranked.find((r) => r.action !== best) ?? ranked[1];
  return {
    action: best,
    cost: expectedCost(best, probabilities, meters),
    runnerUp: runnerUp.action,
    runnerUpCost: runnerUp.cost,
  };
}

/** Does this action send someone out? */
export function sendsSomeone(action: Action): boolean {
  return visit(action) > 0;
}

/**
 * Truck visits avoided compared with the simplest rule (baseline B0): one visit per silent
 * meter, minus the one visit we make if the engine does send someone.
 */
export function dispatchesAvoided(incident: Incident): number {
  return Math.max(0, incident.meterCount - (sendsSomeone(incident.action) ? 1 : 0));
}

/**
 * Dollars saved compared with the simplest rule (baseline B0 in the eval):
 * "send a technician to every meter that goes silent".
 */
export function savedDollars(incident: Incident): number {
  const baseline = incident.meterCount * COSTS.truckRoll;
  const ours =
    visit(incident.action) + (incident.action === 'MANUAL_REVIEW' ? COSTS.manualReview : 0);
  return Math.max(0, baseline - ours);
}
