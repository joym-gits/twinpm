import { NextResponse, type NextRequest } from "next/server";

/** Fast redirect to /login when there is no session cookie. The API remains the authority. */
export function middleware(req: NextRequest) {
  if (!req.cookies.has("twinpm_csrf")) {
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("next", req.nextUrl.pathname);
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!login|api|_next|favicon.ico|.*\\.).*)"],
};
