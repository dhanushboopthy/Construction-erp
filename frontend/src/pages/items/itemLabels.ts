import type { ItemRow } from "@/api/masters";
import type { ItemCategory } from "@/api/types";

export const CATEGORIES: { value: ItemCategory; label: string }[] = [
  { value: "tmt", label: "TMT bars" },
  { value: "pipe", label: "Pipes" },
  { value: "cement", label: "Cement" },
  { value: "wire", label: "Binding wire" },
  { value: "angle", label: "Angles" },
  { value: "channel", label: "Channels" },
  { value: "other", label: "Other" },
];

export const categoryLabel = (c: ItemCategory) => CATEGORIES.find((x) => x.value === c)?.label ?? c;

/** Units an item can be counted in: its base unit, listed units, and "piece" when a
 * theoretical weight per piece is known (G7). */
export function unitNames(item: ItemRow): string[] {
  const names = [item.base_unit, ...item.units.map((u) => u.unit)];
  if (item.weight_per_piece_kg && item.base_unit === "kg" && !names.includes("piece")) {
    names.push("piece");
  }
  return names;
}
