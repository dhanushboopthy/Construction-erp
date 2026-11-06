/**
 * A random v4 UUID for idempotency keys.
 *
 * `crypto.randomUUID` exists only in secure contexts (HTTPS or localhost). On a plain-HTTP address
 * such as a server's bare IP it is undefined and calling it breaks the page, so fall back to
 * `getRandomValues`, which works everywhere.
 */
export function newUuid(): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  const hex = Array.from(bytes, (b, i) => {
    // Version 4 in byte 6, RFC 4122 variant in byte 8.
    const v = i === 6 ? (b & 0x0f) | 0x40 : i === 8 ? (b & 0x3f) | 0x80 : b;
    return v.toString(16).padStart(2, "0");
  }).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
