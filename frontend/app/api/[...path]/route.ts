import { auth } from "@/auth";
import { backendFetch } from "@/lib/backend";

// The browser talks to /api/*; this forwards it to FastAPI with proof of who is signed in.
// The backend is never called from the browser, so there is no CORS and no token in page scripts.
const ROUTES = new Set(["GET dashboard", "POST ask"]);

type Context = { params: Promise<{ path: string[] }> };

async function forward(request: Request, { params }: Context) {
  const path = (await params).path.join("/");
  if (!ROUTES.has(`${request.method} ${path}`)) return Response.json({ detail: "Not found" }, { status: 404 });

  const session = await auth();
  if (!session?.user?.id || !session.user.email) {
    return Response.json({ detail: "Your session has ended. Reload the page to sign in again." }, { status: 401 });
  }

  const user = { id: session.user.id, email: session.user.email, name: session.user.name };
  const hasBody = request.method !== "GET";
  try {
    const res = await backendFetch(user, `/${path}${new URL(request.url).search}`, {
      method: request.method,
      headers: hasBody ? { "Content-Type": "application/json" } : undefined,
      body: hasBody ? await request.text() : undefined,
      signal: request.signal,
    });
    return new Response(res.body, {
      status: res.status,
      headers: { "Content-Type": res.headers.get("Content-Type") ?? "application/json" },
    });
  } catch {
    return Response.json({ detail: "Could not reach the coach. Is the API running?" }, { status: 502 });
  }
}

export { forward as GET, forward as POST };
