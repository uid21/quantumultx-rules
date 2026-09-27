/**
 * Temporary Quantumult X script-echo-response helper for resetting a stuck
 * Claude iOS login state. Disable its rewrite resource as soon as Claude
 * returns to the login screen.
 */

const body = JSON.stringify({
  type: "error",
  error: {
    type: "session_expired",
    message: "Session expired"
  }
});

const headers = {
  "Content-Type": "application/json; charset=utf-8",
  "Cache-Control": "no-store"
};

// Only claude.ai can expire cookies scoped to .claude.ai.
// Keep both cookies separate: Set-Cookie is a repeatable response header.
if (/^https:\/\/claude\.ai\/api\/account(?:[\/?#]|$)/i.test($request.url)) {
  const expires =
    "Path=/; Domain=.claude.ai; Max-Age=0; " +
    "Expires=Thu, 01 Jan 1970 00:00:00 GMT; Secure; HttpOnly; SameSite=Lax";

  headers["Set-Cookie"] = [
    `sessionKey=; ${expires}`,
    `routingHint=; ${expires}`
  ];
}

try {
  $notify("Claude iOS Reset", "已拦截会话接口", $request.url);
} catch (_) {}

$done({
  status: "HTTP/1.1 401 Unauthorized",
  headers,
  body
});
