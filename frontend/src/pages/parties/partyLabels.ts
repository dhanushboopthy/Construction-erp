import type { PartyType } from "@/api/types";

export const TYPE_LABEL: Record<PartyType, string> = {
  customer: "Customer",
  supplier: "Supplier",
  both: "Customer and supplier",
};
