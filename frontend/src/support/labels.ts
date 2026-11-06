import { ApiError } from "@/api/client";

import type { TicketCategory, TicketPriority, TicketStatus } from "./types";

export type TicketTone = "accent" | "good" | "warn" | "critical" | "neutral";

export const CATEGORY: Record<TicketCategory, string> = {
  sign_in: "Signing in",
  billing: "Billing and plan",
  gst_eway: "GST and e-way bills",
  stock: "Stock",
  printing: "Printing",
  other: "Something else",
};
export const CATEGORY_ORDER = Object.keys(CATEGORY) as TicketCategory[];

export const PRIORITY: Record<TicketPriority, { label: string; tone: TicketTone }> = {
  low: { label: "Low", tone: "neutral" },
  normal: { label: "Normal", tone: "neutral" },
  high: { label: "High", tone: "warn" },
  urgent: { label: "Urgent", tone: "critical" },
};
export const PRIORITY_ORDER: TicketPriority[] = ["low", "normal", "high", "urgent"];

export const TICKET_STATUS: Record<TicketStatus, { label: string; tone: TicketTone }> = {
  open: { label: "Open", tone: "accent" },
  in_progress: { label: "In progress", tone: "accent" },
  waiting_on_company: { label: "Waiting on company", tone: "warn" },
  resolved: { label: "Resolved", tone: "good" },
  closed: { label: "Closed", tone: "neutral" },
};
export const TICKET_STATUS_ORDER: TicketStatus[] = [
  "open",
  "in_progress",
  "waiting_on_company",
  "resolved",
  "closed",
];

/** Plain words for the failures a ticket screen can meet. */
export function ticketError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.body.code === "TICKET_CLOSED") {
      return "This ticket is closed, so it cannot take more replies. Raise a new ticket instead.";
    }
    if (error.status === 403) return "Only the person who raised this ticket can close it.";
    return error.message;
  }
  return "Cannot reach the server. Check the network and try again.";
}
