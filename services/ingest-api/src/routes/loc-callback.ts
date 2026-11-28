import { LocCallback, reasonGroup } from '@4p/contracts';
import type { FastifyPluginAsyncTypebox } from '@fastify/type-provider-typebox';
import { Type } from 'typebox';
import type { IngestStore } from '../db/store.js';
import type { Publisher } from '../publisher.js';

/** The callback URL we give Telstra when subscribing meters to Loss of Connectivity. */
export const LOC_CALLBACK_PATH = '/loss-of-connectivity/v0/events';

export interface LocCallbackOptions {
  /** Left out in tests that don't need a database: reports are then only logged. */
  store?: IngestStore;
  /** Hands the events to the engine. Left out = store only. */
  publisher?: Publisher;
}

export const locCallbackRoutes: FastifyPluginAsyncTypebox<LocCallbackOptions> = async (
  app,
  { store, publisher },
) => {
  app.post(
    LOC_CALLBACK_PATH,
    {
      schema: {
        body: LocCallback,
        response: {
          202: Type.Object({ accepted: Type.Integer(), duplicates: Type.Integer() }),
        },
      },
    },
    async (req, reply) => {
      const { subscriptionId, monitoringEventReports } = req.body;
      for (const report of monitoringEventReports) {
        req.log.info(
          {
            subscriptionId,
            msisdn: report.msisdn,
            reasonCode: report.lossOfConnectReason,
            reasonGroup: reasonGroup(report.lossOfConnectReason),
            eventTime: report.eventTime,
          },
          'loss of connectivity reported',
        );
      }
      // If the database or the hand-off fails this throws and Fastify answers 500, so Telstra
      // retries. Repeats are not stored twice but are passed on again (the engine drops them
      // by event id), so nothing is lost when only the hand-off failed.
      if (!store) {
        return reply.code(202).send({ accepted: monitoringEventReports.length, duplicates: 0 });
      }
      const results = await store.addReports(subscriptionId, monitoringEventReports, new Date());
      await publisher?.publish(results.map((r) => r.event));
      const accepted = results.filter((r) => r.isNew).length;
      return reply.code(202).send({ accepted, duplicates: results.length - accepted });
    },
  );
};
