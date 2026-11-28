import { LocCallback, reasonGroup } from '@4p/contracts';
import type { FastifyPluginAsyncTypebox } from '@fastify/type-provider-typebox';
import { Type } from 'typebox';
import type { IngestStore } from '../db/store.js';

/** The callback URL we give Telstra when subscribing meters to Loss of Connectivity. */
export const LOC_CALLBACK_PATH = '/loss-of-connectivity/v0/events';

export interface LocCallbackOptions {
  /** Left out in tests that don't need a database: reports are then only logged. */
  store?: IngestStore;
}

export const locCallbackRoutes: FastifyPluginAsyncTypebox<LocCallbackOptions> = async (
  app,
  { store },
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
      // If the database is down this throws and Fastify answers 500, so Telstra can retry.
      const stored = store
        ? await store.addReports(subscriptionId, monitoringEventReports, new Date())
        : null;
      const accepted = stored ? stored.length : monitoringEventReports.length;
      return reply
        .code(202)
        .send({ accepted, duplicates: monitoringEventReports.length - accepted });
    },
  );
};
