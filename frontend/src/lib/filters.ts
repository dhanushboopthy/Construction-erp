/** True when `needle` (typed in a list's search box) appears in any of the values, ignoring case. */
export function includesText(needle: string, ...values: (string | number | null | undefined)[]) {
  const q = needle.trim().toLowerCase();
  return (
    !q ||
    values.some((v) =>
      String(v ?? "")
        .toLowerCase()
        .includes(q),
    )
  );
}
