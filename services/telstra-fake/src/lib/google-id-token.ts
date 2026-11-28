/**
 * Our Cloud Run services are private: a caller needs a Google ID token for the target URL.
 * On Cloud Run the metadata server hands one out for the service's own identity. Locally there
 * is no metadata server, so we send no token (Compose has no auth between services).
 */
const METADATA =
  'http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity';

export async function authHeaders(url: string): Promise<Record<string, string>> {
  if (!process.env.K_SERVICE) return {}; // K_SERVICE is set by Cloud Run
  const { origin, hostname } = new URL(url);
  if (!hostname.endsWith('.run.app')) return {};
  const res = await fetch(`${METADATA}?audience=${encodeURIComponent(origin)}`, {
    headers: { 'Metadata-Flavor': 'Google' },
  });
  if (!res.ok) throw new Error(`metadata server answered ${res.status}`);
  return { authorization: `Bearer ${await res.text()}` };
}
