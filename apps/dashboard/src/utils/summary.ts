/**
 * The plain-English summary on the verdict card, in the same words as the engine's
 * template_summary() in services/engine/src/engine/summary.py.
 *
 * With the live backend the engine sends `summary` and `notice` inside the Verdict (written by
 * Gemini when it is switched on). The mock data has no engine behind it, so it uses this copy.
 */
import type { Action, Cause, Verdict } from '../types.ts';

const CAUSE_WORDS: Record<Cause, string> = {
  POWER: 'a power outage',
  NETWORK: 'a Telstra mobile network outage',
  METER_FAULT: 'a faulty meter',
  TAMPER: 'possible tampering with a meter',
};

const ACTION_WORDS: Record<Action, string> = {
  DISPATCH_POWER_CREW: 'A power crew has been sent.',
  WAIT_FOR_NETWORK: 'No one has been sent; the meters should reconnect when the network is back.',
  DISPATCH_METER_TECH: 'A meter technician has been sent.',
  INVESTIGATE_TAMPER: 'The meter has been flagged for a tamper investigation.',
  MANUAL_REVIEW: 'The engine is not sure enough to act, so an operator needs to review it.',
};

type Decided = Pick<Verdict, 'meterCount' | 'cause' | 'confidence' | 'action'>;

export function templateSummary(v: Decided): { summary: string; notice: string } {
  const meters = `${v.meterCount} meter${v.meterCount === 1 ? '' : 's'}`;
  const summary =
    `${meters} went silent. The most likely cause is ${CAUSE_WORDS[v.cause]} ` +
    `(${Math.round(v.confidence * 100)}% confidence). ${ACTION_WORDS[v.action]}`;
  const notice =
    v.cause === 'POWER' && v.action === 'DISPATCH_POWER_CREW'
      ? 'We are aware of a power outage in your area and a crew is on the way. ' +
        'We will update you when power is restored.'
      : '';
  return { summary, notice };
}
