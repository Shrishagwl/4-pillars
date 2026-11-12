import { LocCallback, reasonGroup } from '@4p/contracts';
import type { FastifyPluginAsyncTypebox } from '@fastify/type-provider-typebox';
import { Type } from 'typebox';

/** The callback URL we give Telstra when subscribing meters to Loss of Connectivity. */
export const LOC_CALLBACK_PATH = '/loss-of-connectivity/v0/events';

export const locCallbackRoutes: FastifyPluginAsyncTypebox = async (app) => {
  app.post(
    LOC_CALLBACK_PATH,
    {
      schema: {
        body: LocCallback,
        response: { 202: Type.Object({ accepted: Type.Integer() }) },
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
      // TODO(#14): store each report in the ingest schema.
      // TODO(#22): publish a MeterSilentEvent per report to Pub/Sub for the engine.
      return reply.code(202).send({ accepted: monitoringEventReports.length });
    },
  );
};
