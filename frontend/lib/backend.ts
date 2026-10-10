import "server-only";
import { SignJWT } from "jose";

const API_URL = process.env.API_URL ?? "http://127.0.0.1:8000";

export type BackendUser = { id: string; email: string; name?: string | null };

function secret() {
  const value = process.env.API_JWT_SECRET;
  if (!value) throw new Error("API_JWT_SECRET is not set");
  return new TextEncoder().encode(value);
}

/** Call FastAPI as this user. The token proves who they are and only lives for a minute. */
export async function backendFetch(user: BackendUser, path: string, init: RequestInit = {}) {
  const token = await new SignJWT({ email: user.email, name: user.name ?? undefined })
    .setProtectedHeader({ alg: "HS256" })
    .setSubject(user.id)
    .setIssuer("fit-me-coach-web")
    .setAudience("fit-me-coach-api")
    .setIssuedAt()
    .setExpirationTime("60s")
    .sign(secret());

  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${token}`);
  return fetch(`${API_URL}${path}`, { ...init, headers, cache: "no-store" });
}
