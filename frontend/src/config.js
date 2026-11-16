// Same origin in dev (Vite proxy) and in production (nginx sidecar).
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

// Operator write token. Open the site once with ?write_token=<value>; it is
// kept in sessionStorage, scrubbed from the URL, and sent as X-Write-Token.
// It unlocks decisions and approvals and exempts the session from the triage
// rate limit. The plain link is read-only, and says so when you try.
const TOKEN_KEY = "madison_demo_write_token";
const ACTOR_KEY = "madison_demo_actor";

function captureTokenFromUrl() {
  try {
    const url = new URL(window.location.href);
    const token = url.searchParams.get("write_token");
    if (token) {
      sessionStorage.setItem(TOKEN_KEY, token);
      url.searchParams.delete("write_token");
      window.history.replaceState({}, "", url.pathname + url.search + url.hash);
    }
  } catch { /* storage blocked */ }
}
captureTokenFromUrl();

export function writeToken() {
  try { return sessionStorage.getItem(TOKEN_KEY) || ""; } catch { return ""; }
}

export function authHeaders() {
  const token = writeToken();
  return token ? { "X-Write-Token": token } : {};
}

// Who the operator says they are. Recorded and used for separation of
// duties (a proposer cannot approve), never trusted as identity.
export function actorName() {
  try { return sessionStorage.getItem(ACTOR_KEY) || "AP team lead"; } catch { return "AP team lead"; }
}

export function setActorName(name) {
  try { sessionStorage.setItem(ACTOR_KEY, name); } catch { /* storage blocked */ }
}
