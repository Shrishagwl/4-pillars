/**
 * The cost model, copied from the engine (services/engine/src/engine/decision.py) so the
 * dashboard can explain the engine's choice in dollars.
 *
 * Every number is a placeholder until task 3 ("Set the cost of each decision") is done.
 * When the real costs are agreed, change them here AND in the engine.
 */
import type { Action, Cause, Incident } from '../types.ts';

export const COSTS = {
  truckRoll: 300, // one technician visit
  powerCrew: 800, // one power crew call-out
  latePowerPerMeter: 10, // a power cut we did not act on, per customer
  meterLeftBroken: 100, // a faulty meter we did not send anyone to
  missedTamper: 500, // tampering we did not investigate
  manualReview: 8, // ten minutes of an operator
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
