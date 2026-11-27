/**
 * Labels and colours for each cause and action, kept in one place so the map, the cards and
 * the lists always match. Colours are from the Telstra palette (see index.css).
 */
import type { Action, Cause, Incident } from '../types.ts';

export const CAUSES: Cause[] = ['POWER', 'NETWORK', 'METER_FAULT', 'TAMPER'];

interface CauseStyle {
  label: string; // "Power outage"
  short: string; // "Power", used next to the probability bars
  color: string; // strong colour: map dots, bars
  tint: string; // light background for pills
}

export const CAUSE_STYLE: Record<Cause, CauseStyle> = {
  POWER: { label: 'Power outage', short: 'Power', color: '#f44e1a', tint: '#ffddd1' },
  NETWORK: { label: 'Network outage', short: 'Network', color: '#0d54ff', tint: '#d8f0fe' },
  METER_FAULT: { label: 'Meter fault', short: 'Meter fault', color: '#93713b', tint: '#f5ede2' },
  TAMPER: { label: 'Tamper', short: 'Tamper', color: '#69001b', tint: '#f6dfe4' },
};

/** Grey for meters that are reporting normally. */
export const ONLINE_COLOR = '#a0a0a0';

/** Shown instead of the cause when the engine wants a person to decide. */
export const REVIEW_STYLE = { label: 'Needs review', color: '#da1e28', tint: '#fbe0e1' };

interface ActionText {
  button: string; // text on the main button
  done: string; // text once the operator has clicked it
}

export const ACTION_TEXT: Record<Action, ActionText> = {
  DISPATCH_POWER_CREW: { button: 'Dispatch power crew', done: 'Power crew dispatched' },
  WAIT_FOR_NETWORK: { button: 'Hold crews', done: 'Crews on hold' },
  DISPATCH_METER_TECH: { button: 'Send meter technician', done: 'Technician sent' },
  INVESTIGATE_TAMPER: { button: 'Investigate tamper', done: 'Investigation opened' },
  MANUAL_REVIEW: { button: 'Review manually', done: 'Marked as reviewed' },
};

/** One sentence for the "Recommended action" card. */
export function actionSentence(incident: Incident): string {
  const transformers = incident.transformerIds.join(', ');
  switch (incident.action) {
    case 'DISPATCH_POWER_CREW':
      return `Dispatch a power crew to transformer ${transformers}`;
    case 'WAIT_FOR_NETWORK':
      return `Hold crews: Telstra network outage in ${incident.suburb}`;
    case 'DISPATCH_METER_TECH':
      return `Send a technician to meter ${incident.meterIds[0]}`;
    case 'INVESTIGATE_TAMPER':
      return `Investigate possible tampering at meter ${incident.meterIds[0]}`;
    case 'MANUAL_REVIEW':
      return 'Check this one by hand before sending anyone';
  }
}

export function needsReview(incident: Incident): boolean {
  return incident.action === 'MANUAL_REVIEW';
}

/** Turns engine words like DISPATCH_POWER_CREW into "dispatch power crew" for display. */
export function humanise(text: string): string {
  return text.replace(/\b[A-Z]+(?:_[A-Z]+)+\b|\b(POWER|NETWORK|TAMPER)\b/g, (word) =>
    word.toLowerCase().replaceAll('_', ' '),
  );
}
