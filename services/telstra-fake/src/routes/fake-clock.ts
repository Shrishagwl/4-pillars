import type { FastifyPluginAsyncTypebox } from '@fastify/type-provider-typebox';
import { Type } from 'typebox';
import type { Clock } from '../lib/clock.js';

/** Not part of Telstra's API: lets the twin line the fake's clock up with a scenario. */
export const FAKE_CLOCK_PATH = '/fake/clock';

export const fakeClockRoutes: FastifyPluginAsyncTypebox<{ clock: Clock }> = async (
  app,
  { clock },
) => {
  app.get(FAKE_CLOCK_PATH, async () => ({ now: clock.now().toISOString() }));

  app.put(
    FAKE_CLOCK_PATH,
    { schema: { body: Type.Object({ now: Type.String({ format: 'date-time' }) }) } },
    async (req) => {
      clock.set(new Date(req.body.now));
      return { now: clock.now().toISOString() };
    },
  );

  app.delete(FAKE_CLOCK_PATH, async (_req, reply) => {
    clock.reset();
    return reply.code(204).send();
  });
};
