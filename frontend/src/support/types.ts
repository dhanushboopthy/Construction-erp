// Milestone 22 (support tickets). Written by hand until `make gen-api` runs. No amounts here.

export type TicketCategory = "sign_in" | "billing" | "gst_eway" | "stock" | "printing" | "other";
export type TicketPriority = "low" | "normal" | "high" | "urgent";
export type TicketStatus = "open" | "in_progress" | "waiting_on_company" | "resolved" | "closed";
export type AuthorKind = "company_user" | "platform_admin";

export interface TicketMessage {
  id: number;
  author_kind: AuthorKind;
  author_name: string;
  body: string;
  created_at: string;
}

export interface TicketRow {
  id: number;
  /** "T-000012" */
  number: string;
  subject: string;
  category: TicketCategory;
  priority: TicketPriority;
  status: TicketStatus;
  raised_by_name: string;
  created_at: string;
  last_reply_at: string | null;
  unread: boolean;
}

export interface TicketDetail extends TicketRow {
  assigned_admin_name: string | null;
  closed_at: string | null;
  /** The signed-in user raised it and it is not closed (decided by the server). */
  can_close: boolean;
  messages: TicketMessage[];
}

export interface TicketList {
  items: TicketRow[];
  total: number;
}

export interface NewTicket {
  subject: string;
  category: TicketCategory;
  priority: TicketPriority;
  body: string;
}

export interface AdminTicketRow extends TicketRow {
  tenant_id: number;
  tenant_name: string;
  tenant_slug: string;
  assigned_admin_id: number | null;
  assigned_admin_name: string | null;
}

export interface AdminTicketDetail extends AdminTicketRow {
  closed_at: string | null;
  messages: TicketMessage[];
}

export interface TicketCounts {
  open: number;
  in_progress: number;
  waiting_on_company: number;
  resolved: number;
  closed: number;
  urgent_open: number;
  unassigned: number;
}

export interface AdminTicketPage {
  items: AdminTicketRow[];
  total: number;
  limit: number;
  offset: number;
  counts: TicketCounts;
}

export interface AdminTicketFilters {
  status?: string;
  priority?: string;
  tenant_id?: number | string;
  assigned?: string;
  q?: string;
  limit?: number;
  offset?: number;
}

export interface AdminTicketReply {
  body?: string;
  status?: TicketStatus;
}

export interface AdminTicketPatch {
  status?: TicketStatus;
  priority?: TicketPriority;
  assigned_admin_id?: number | null;
}
