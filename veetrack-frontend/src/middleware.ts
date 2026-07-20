import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const PROTECTED = ["/feed", "/discover", "/alerts", "/profile", "/story", "/admin"];
const AUTH_PAGES = ["/login", "/register"];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Check for our session cookie that login sets
  const hasSession = request.cookies.has("vt_session");

  const isProtected = PROTECTED.some((p) => pathname.startsWith(p));
  const isAuthPage = AUTH_PAGES.some((p) => pathname.startsWith(p));

  // Unauthenticated user hitting a protected route → login
  if (isProtected && !hasSession) {
    const loginUrl = request.nextUrl.clone();
    loginUrl.pathname = "/login";
    loginUrl.searchParams.set("next", pathname);
    return NextResponse.redirect(loginUrl);
  }

  // Already logged in user hitting login/register → feed
  if (isAuthPage && hasSession) {
    const feedUrl = request.nextUrl.clone();
    feedUrl.pathname = "/feed";
    feedUrl.search = "";
    return NextResponse.redirect(feedUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|vee_logo.jpeg|vee_technologies_logo.jpeg|api/).*)",
  ],
};
