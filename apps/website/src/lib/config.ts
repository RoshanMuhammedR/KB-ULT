// Where the marketing site hands users off to reach the product. In dev the product runs at
// http://<domain>:3000; in prod set scheme=https and leave the port empty so it's just
// https://<domain>. Driven by NEXT_PUBLIC_PRODUCT_SCHEME / NEXT_PUBLIC_PRODUCT_PORT.

const SCHEME = process.env.NEXT_PUBLIC_PRODUCT_SCHEME ?? "http";
const PORT = process.env.NEXT_PUBLIC_PRODUCT_PORT ?? "3000";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Base origin for a tenant's product app, e.g. `http://acme.test:3000`. */
export function productOrigin(domain: string): string {
  const host = domain.trim().toLowerCase();
  return PORT ? `${SCHEME}://${host}:${PORT}` : `${SCHEME}://${host}`;
}

/** The product bootstrap URL that redeems a handoff code and drops the user into the app. */
export function productBootstrapUrl(domain: string, code: string, remember: boolean): string {
  const params = new URLSearchParams({ code });
  if (remember) params.set("remember", "1");
  return `${productOrigin(domain)}/bootstrap?${params.toString()}`;
}

/** The product's domain-scoped login page. */
export function productLoginUrl(domain: string): string {
  return `${productOrigin(domain)}/login`;
}
