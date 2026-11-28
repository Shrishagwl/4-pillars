import {
  LOC_SUBSCRIPTION_PATHS,
  type LocSubscriptionError,
  LocSubscriptionRequest,
  type LocSubscriptionsResponse,
} from '@4p/contracts';
import type { FastifyPluginAsyncTypebox } from '@fastify/type-provider-typebox';
import type { FastifyError } from 'fastify';
import { Type } from 'typebox';
import type { LocStore } from '../lib/loc-store.js';
import { checkTelstraHeaders, sendErrors } from '../lib/telstra-errors.js';

/** Not part of Telstra's API: the twin calls this to make a SIM "lose connectivity". */
export const LOC_TRIGGER_PATH = '/fake/loss-of-connectivity/events';

const LocEventBody = Type.Object({
  msisdn: Type.String({ minLength: 1 }),
  lossOfConnectReason: Type.Integer({ minimum: 0, maximum: 8 }),
  eventTime: Type.Optional(Type.String({ format: 'date-time' })),
});

const SUPPORT = 'If the issue persists, contact support at telstradev@team.telstra.com.';

export const lossOfConnectivityRoutes: FastifyPluginAsyncTypebox<{ store: LocStore }> = async (
  app,
  { store },
) => {
  // Telstra's docs send Content-Type: application/json on GET and DELETE too, with no body.
  app.removeContentTypeParser('application/json');
  app.addContentTypeParser('application/json', { parseAs: 'string' }, (_req, body, done) => {
    try {
      done(null, body === '' ? undefined : JSON.parse(body as string));
    } catch (err) {
      done(Object.assign(err as Error, { statusCode: 400 }), undefined);
    }
  });

  // Bad bodies get Telstra's errors array, not Fastify's default error shape.
  app.setErrorHandler((err: FastifyError, _req, reply) => {
    if (err.validation) {
      const first = err.validation[0];
      const field = first?.instancePath?.replace(/^\//, '').replaceAll('/', '.') || 'body';
      return sendErrors(reply, 400, [
        {
          code: 'FIELD_INVALID',
          issue: field,
          location: 'body',
          fieldName: field,
          suggested_action: `Check ${field}: ${first?.message ?? 'invalid value'}.`,
        },
      ]);
    }
    if (err.statusCode && err.statusCode < 500) {
      return sendErrors(reply, err.statusCode, [
        {
          code: 'FIELD_INVALID',
          issue: err.message,
          location: 'body',
          suggested_action: 'Check the request body.',
        },
      ]);
    }
    reply.log.error(err);
    return sendErrors(reply, 500, [
      {
        code: 'UNKNOWN',
        issue: 'Unknown',
        location: 'service',
        suggested_action: `Please try again. ${SUPPORT}`,
      },
    ]);
  });

  app.addHook('preHandler', async (req, reply) => {
    if (!req.url.startsWith('/fake/') && !checkTelstraHeaders(req, reply)) return reply;
  });

  for (const base of LOC_SUBSCRIPTION_PATHS) {
    app.post(base, { schema: { body: LocSubscriptionRequest } }, async (req, reply) => {
      // Duplicate MSISDNs anywhere in the payload are rejected outright.
      const all = req.body.subscriptions.flatMap((s) => s.msisdn);
      const dupe = all.find((m, i) => all.indexOf(m) !== i);
      if (dupe) {
        return sendErrors(reply, 400, [
          {
            code: 'FIELD_INVALID',
            issue: 'Duplicate msisdn values are not allowed.',
            location: 'body',
            fieldName: 'msisdn',
            value: dupe,
            suggested_action: 'Send each msisdn only once per request.',
          },
        ]);
      }

      const created: LocSubscriptionsResponse['subscriptions'] = [];
      const errors: LocSubscriptionError[] = [];
      for (const { msisdn: list, notificationDestination } of req.body.subscriptions) {
        for (const msisdn of list) {
          const sub = store.add(msisdn, notificationDestination);
          if (sub) created.push({ ...sub, status: 201 });
          else
            errors.push({
              type: 'SUBSCRIPTION_EXISTS',
              'message-content': `A subscription already exists for this device - ${msisdn}`,
              status: 409,
              msisdn,
              notificationDestination,
            });
        }
      }
      const status = errors.length === 0 ? 201 : 207;
      return reply.code(status).send({
        'correlation-id': req.headers['correlation-id'] as string,
        status,
        timeStamp: Date.now(),
        message: status === 201 ? 'successful' : 'partial_success',
        subscriptions: created,
        ...(errors.length ? { errors } : {}),
      });
    });

    app.get(
      base,
      {
        schema: {
          querystring: Type.Object({
            limit: Type.Optional(Type.Integer({ minimum: 1, maximum: 1000 })),
            cursor: Type.Optional(Type.String()),
          }),
        },
      },
      async (req) => {
        const limit = req.query.limit ?? 100;
        const { items, nextCursor } = store.page(limit, req.query.cursor);
        return { subscriptions: items, ...(nextCursor ? { nextCursor } : {}), limit };
      },
    );

    const notFound = (id: string) => ({
      code: 'RESOURCE_NOT_FOUND',
      issue: 'The requested subscriptionId was not found.',
      location: 'path',
      value: id,
      fieldName: 'subscriptionId',
      suggested_action: `Check the subscriptionId and try again. ${SUPPORT}`,
    });

    app.get<{ Params: { subscriptionId: string } }>(
      `${base}/:subscriptionId`,
      async (req, reply) => {
        const sub = store.get(req.params.subscriptionId);
        return sub ?? sendErrors(reply, 404, [notFound(req.params.subscriptionId)]);
      },
    );

    app.delete<{ Params: { subscriptionId: string } }>(
      `${base}/:subscriptionId`,
      async (req, reply) => {
        if (!store.remove(req.params.subscriptionId)) {
          return sendErrors(reply, 404, [notFound(req.params.subscriptionId)]);
        }
        return reply.code(204).send();
      },
    );
  }

  // One event or a batch. Answers with what happened to each callback, for tests and the twin.
  app.post(
    LOC_TRIGGER_PATH,
    {
      schema: {
        body: Type.Union([LocEventBody, Type.Object({ events: Type.Array(LocEventBody) })]),
      },
    },
    async (req) => {
      const events = 'events' in req.body ? req.body.events : [req.body];
      const result = await store.deliver(events);
      for (const d of result.deliveries) {
        req.log.info({ ...d }, 'loss of connectivity callback sent');
      }
      return result;
    },
  );
};
