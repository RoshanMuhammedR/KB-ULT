// Where this marketing site sends people to reach the product. In production the two apps
// share one origin — Caddy routes `/app/*` to the product and everything else here — so the
// default is a relative path. In dev the product runs on its own port, so point
// NEXT_PUBLIC_PRODUCT_URL at e.g. http://localhost:3000/app.

export const PRODUCT_URL = process.env.NEXT_PUBLIC_PRODUCT_URL ?? "/app";

export const LOGIN_URL = `${PRODUCT_URL}/login`;
export const REGISTER_URL = `${PRODUCT_URL}/register`;
