import {
  ArrowLeftRight,
  CalendarCheck,
  ClipboardList,
  FilePlus2,
  FileSpreadsheet,
  HandCoins,
  PackagePlus,
  ShieldCheck,
  Tag,
  UserPlus,
  type LucideIcon,
} from "lucide-react";

import type { Role } from "@/api/types";
import { modulesFor } from "@/modules";

/** Things people do many times a day. Each lives inside a module and inherits its roles. */
export interface QuickAction {
  id: string;
  label: string;
  hint: string;
  path: string;
  module: string;
  icon: LucideIcon;
  keywords?: string;
}

const ACTIONS: QuickAction[] = [
  {
    id: "bill",
    label: "New bill",
    hint: "GST invoice for a customer",
    path: "/sales/new",
    module: "/sales",
    icon: FilePlus2,
    keywords: "sale invoice sell",
  },
  {
    id: "purchase",
    label: "New purchase",
    hint: "Supplier bill with landed cost",
    path: "/purchases/new",
    module: "/purchases",
    icon: PackagePlus,
    keywords: "buy supplier",
  },
  {
    id: "payment",
    label: "Record a payment",
    hint: "Cash, UPI or bank receipt",
    path: "/payments",
    module: "/payments",
    icon: HandCoins,
    keywords: "receipt collect money",
  },
  {
    id: "rates",
    label: "Set today's rates",
    hint: "Market rate per item",
    path: "/rates",
    module: "/rates",
    icon: Tag,
    keywords: "price",
  },
  {
    id: "transfer",
    label: "Move stock",
    hint: "Transfer between shop and godown",
    path: "/stock/transfers",
    module: "/stock",
    icon: ArrowLeftRight,
    keywords: "transfer godown",
  },
  {
    id: "count",
    label: "Count stock",
    hint: "Physical count and variance",
    path: "/stock/counts",
    module: "/stock",
    icon: ClipboardList,
    keywords: "audit physical",
  },
  {
    id: "close",
    label: "Close the day",
    hint: "Drawer cash and day lock",
    path: "/reports",
    module: "/reports",
    icon: CalendarCheck,
    keywords: "closing cash drawer",
  },
  {
    id: "gst",
    label: "GST returns",
    hint: "GSTR-1, GSTR-3B and 2B matching",
    path: "/reports/gst",
    module: "/reports",
    icon: FileSpreadsheet,
    keywords: "gstr tax",
  },
  {
    id: "users",
    label: "Add a user",
    hint: "Staff sign-ins and roles",
    path: "/settings/users",
    module: "/settings",
    icon: UserPlus,
    keywords: "staff login",
  },
  {
    id: "system",
    label: "System health",
    hint: "Backups, storage and checks",
    path: "/settings/system",
    module: "/settings",
    icon: ShieldCheck,
    keywords: "backup status",
  },
];

export function actionsFor(role: Role): QuickAction[] {
  const allowed = new Set(modulesFor(role).map((m) => m.path));
  return ACTIONS.filter((a) => allowed.has(a.module));
}
