/** Up to two capital letters: first letters of the first and last word of a name. */
export function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "?";
  const first = words[0] ?? "";
  const last = words.length > 1 ? (words[words.length - 1] ?? "") : "";
  return `${first.charAt(0)}${last.charAt(0)}`.toUpperCase();
}

/** Navy or orange, picked from the name so a person keeps the same colour everywhere. */
export function avatarTone(name: string): "navy" | "orange" {
  let sum = 0;
  for (const ch of name) sum += ch.charCodeAt(0);
  return sum % 2 === 0 ? "navy" : "orange";
}
