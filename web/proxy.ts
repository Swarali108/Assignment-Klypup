import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * Sign-in gate (Next 16 "proxy", the renamed middleware). Anyone without a valid session goes to /login.
 * The session is checked by asking the data service, which owns the signing secret. /api, /login and
 * static files are excluded by the matcher; /api answers 401 JSON on its own.
 */
const API_ORIGIN = (process.env.API_ORIGIN || process.env.API_INTERNAL_ORIGIN || "http://127.0.0.1:8000").replace(/\/+$/, "");

export async function proxy(request: NextRequest) {
  const cookie = request.headers.get("cookie") ?? "";
  let signedIn = false;
  let expired = false;
  if (cookie.includes("aurelia_session=")) {
    try {
      const res = await fetch(`${API_ORIGIN}/api/auth/me`, { headers: { cookie }, cache: "no-store" });
      signedIn = res.ok;
      expired = res.status === 401;
    } catch {
      // The data service is briefly unreachable (a restart): keep the cookie so the viewer is not signed out.
      signedIn = false;
    }
  }
  if (signedIn) return NextResponse.next();
  const url = new URL("/login", request.url);
  if (request.nextUrl.pathname !== "/") url.searchParams.set("next", request.nextUrl.pathname + request.nextUrl.search);
  const response = NextResponse.redirect(url);
  if (expired) response.cookies.delete("aurelia_session");
  return response;
}

export const config = {
  matcher: ["/((?!api/|login(?:/|$)|_next/static/|_next/image|icon.svg$|favicon.ico$).*)"],
};
