import { API_URL } from "./config";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function readError(res: Response): Promise<string> {
  const body = await res.json().catch(() => ({}));
  return (body as { detail?: string }).detail ?? `Request failed with ${res.status}`;
}

type TokenResponse = {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
};

export type RegisterInput = {
  domain: string;
  email: string;
  password: string;
  name?: string;
};

/** Create the workspace + its owner user; returns a fresh session (auto-login). */
export async function register(input: RegisterInput): Promise<TokenResponse> {
  const res = await fetch(`${API_URL}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
    cache: "no-store"
  });
  if (!res.ok) throw new ApiError(res.status, await readError(res));
  return (await res.json()) as TokenResponse;
}

/** Exchange the just-issued access token for a single-use cross-domain handoff code. */
export async function issueHandoff(accessToken: string): Promise<{ code: string; expires_in: number }> {
  const res = await fetch(`${API_URL}/auth/handoff/issue`, {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}` },
    cache: "no-store"
  });
  if (!res.ok) throw new ApiError(res.status, await readError(res));
  return (await res.json()) as { code: string; expires_in: number };
}
