/**
 * Global configuration and base API URL resolution for OrgBridge War Room.
 */

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ||
  (process.env.NODE_ENV === "development"
    ? "http://localhost:8000"
    : "https://orgbridge-ai-backend.onrender.com");
