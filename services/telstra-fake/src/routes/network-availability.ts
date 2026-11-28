import { AU_STATES, NETWORK_STATUS_PATH } from '@4p/contracts';
import type { FastifyPluginAsyncTypebox } from '@fastify/type-provider-typebox';
import { Type } from 'typebox';
import type { OutageStore } from '../lib/outage-store.js';
import { checkTelstraHeaders, sendErrors, type TelstraError } from '../lib/telstra-errors.js';

/** Not part of Telstra's API: the twin adds and ends outages here. */
export const FAKE_OUTAGES_PATH = '/fake/network-availability/outages';

const NewOutageBody = Type.Object({
  state: Type.String({ minLength: 1 }),
  suburb: Type.String({ minLength: 1 }),
  postcode: Type.String({ pattern: '^[0-9]{4}$' }),
  start: Type.String({ format: 'date-time' }),
  end: Type.Optional(Type.String({ format: 'date-time' })),
  root_cause: Type.Optional(Type.String()),
  description: Type.Optional(Type.String()),
  is_planned: Type.Optional(Type.Boolean()),
  technology: Type.Optional(Type.String()),
  affected_area: Type.Optional(Type.String({ pattern: '^MULTIPOLYGON' })),
});

/** What the API says about each query parameter when it is missing or wrong. */
function checkQuery(query: Record<string, string | undefined>): TelstraError[] {
  const errors: TelstraError[] = [];
  for (const field of ['suburb', 'state', 'postcode'] as const) {
    if (!query[field]) {
      errors.push({
        code: 'FIELD_MISSING',
        issue: field,
        field,
        location: 'query',
        suggested_action: `Please provide the ${field}.`,
      });
    }
  }
  const { state, postcode } = query;
  if (state && !(AU_STATES as readonly string[]).includes(state.toUpperCase())) {
    errors.push({
      code: 'FIELD_INVALID',
      issue: 'state',
      field: 'state',
      value: state,
      location: 'query',
      suggested_action: `Use one of ${AU_STATES.join(', ')}.`,
    });
  }
  if (postcode && !/^[0-9]{4}$/.test(postcode)) {
    errors.push({
      code: 'FIELD_INVALID',
      issue: 'postcode',
      field: 'postcode',
      value: postcode,
      location: 'query',
      suggested_action: 'The postcode must contain four digits.',
    });
  }
  return errors;
}

export const networkAvailabilityRoutes: FastifyPluginAsyncTypebox<{ store: OutageStore }> = async (
  app,
  { store },
) => {
  app.get(NETWORK_STATUS_PATH, async (req, reply) => {
    reply.header('content-language', 'en-au'); // returned on successes and errors
    if (!checkTelstraHeaders(req, reply, 'field')) return reply;
    const query = req.query as Record<string, string | undefined>;
    const errors = checkQuery(query);
    if (errors.length) return sendErrors(reply, 400, errors);

    const { suburb, state, postcode } = query as {
      suburb: string;
      state: string;
      postcode: string;
    };
    return {
      'correlation-id': req.headers['correlation-id'] as string,
      status: 200,
      timeStamp: Date.now(),
      ...store.query(suburb, state, postcode),
    };
  });

  app.post(FAKE_OUTAGES_PATH, { schema: { body: NewOutageBody } }, async (req, reply) => {
    const id = store.add(req.body);
    req.log.info({ id, suburb: req.body.suburb, start: req.body.start }, 'fake outage added');
    return reply.code(201).send({ id });
  });

  app.post<{ Params: { id: string }; Body: { end?: string } }>(
    `${FAKE_OUTAGES_PATH}/:id/end`,
    async (req, reply) => {
      const when = req.body?.end ?? new Date().toISOString();
      return store.end(req.params.id, when)
        ? { id: req.params.id, end: when }
        : reply.code(404).send();
    },
  );

  app.delete(FAKE_OUTAGES_PATH, async (_req, reply) => {
    store.clear();
    return reply.code(204).send();
  });
};
