import type { FastifyPluginAsyncTypebox } from '@fastify/type-provider-typebox';
import { Type } from 'typebox';

export interface HealthOptions {
  service: string;
  version: string;
}

export const healthRoutes: FastifyPluginAsyncTypebox<HealthOptions> = async (app, opts) => {
  app.get(
    '/health',
    {
      schema: {
        response: {
          200: Type.Object({
            status: Type.Literal('ok'),
            service: Type.String(),
            version: Type.String(),
          }),
        },
      },
    },
    async () => ({ status: 'ok' as const, service: opts.service, version: opts.version }),
  );
};
