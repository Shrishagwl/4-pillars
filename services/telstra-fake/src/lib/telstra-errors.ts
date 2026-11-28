import type { FastifyReply, FastifyRequest } from 'fastify';

/** One item of Telstra's `errors` array (LoC and Network Availability use the same shape). */
export interface TelstraError {
  code: string;
  issue: string;
  suggested_action: string;
  location?: string;
  fieldName?: string;
  field?: string;
  value?: unknown;
}

export function sendErrors(reply: FastifyReply, status: number, errors: TelstraError[]) {
  return reply.code(status).send({ errors });
}

const UUID_V4 = /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$/;

/**
 * The checks the real gateway does on every call: a Bearer token and a UUID v4 correlation id.
 * We accept any token (the fake has no users), but a missing one gets the same 401 Telstra sends.
 * `fieldName` is what LoC calls the field; Network Availability calls it `field`.
 * Returns true when the request may go on.
 */
export function checkTelstraHeaders(
  req: FastifyRequest,
  reply: FastifyReply,
  fieldKey: 'fieldName' | 'field' = 'fieldName',
): boolean {
  const auth = req.headers.authorization ?? '';
  if (!/^Bearer \S+$/.test(auth)) {
    sendErrors(reply, 401, [
      {
        code: 'TOKEN_INVALID',
        issue: 'The access token is invalid.',
        location: 'header',
        [fieldKey]: 'authorization',
        suggested_action:
          'Check the Authorization header. It should contain a valid Bearer access token.',
      },
    ]);
    return false;
  }
  const correlationId = req.headers['correlation-id'];
  if (typeof correlationId !== 'string' || !UUID_V4.test(correlationId)) {
    sendErrors(reply, 400, [
      {
        code: correlationId ? 'FIELD_INVALID' : 'FIELD_MISSING',
        issue: 'correlation-id',
        location: 'header',
        [fieldKey]: 'correlation-id',
        suggested_action: 'Send a new UUID v4 in the correlation-id header on every request.',
      },
    ]);
    return false;
  }
  return true;
}
