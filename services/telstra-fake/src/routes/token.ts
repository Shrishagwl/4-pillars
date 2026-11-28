import type { FastifyPluginAsync } from 'fastify';

/** Same path as Telstra's OAuth2 token endpoint, so the gateway only swaps the base URL. */
export const TOKEN_PATH =
  '/og-network-auth-prod/api/realms/network-auth/protocol/openid-connect/token';

/**
 * Client-credentials token, like the real one. Any client id and secret work: the fake has no
 * accounts, it only checks that the request has the right shape.
 */
export const tokenRoutes: FastifyPluginAsync = async (app) => {
  app.addContentTypeParser(
    'application/x-www-form-urlencoded',
    { parseAs: 'string' },
    (_req, body, done) => done(null, Object.fromEntries(new URLSearchParams(body as string))),
  );

  app.post(TOKEN_PATH, async (req, reply) => {
    const form = (req.body ?? {}) as Record<string, string>;
    if (form.grant_type !== 'client_credentials' || !form.client_id || !form.client_secret) {
      return reply.code(400).send({ error: 'invalid_request' });
    }
    return {
      access_token: `fake-${crypto.randomUUID()}`,
      token_type: 'Bearer',
      expires_in: 3600,
      scope: form.scope ?? '',
    };
  });
};
