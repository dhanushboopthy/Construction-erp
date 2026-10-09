import type { Role } from "@/api/types";

/** Navigation for the whole ERP. `milestone` marks screens not built yet (docs/ROADMAP.md). */
export interface ModuleLink {
  path: string;
  label: string;
  shortcut: string; // Alt + this key
  roles: Role[];
  milestone?: number;
  purpose: string;
}

const ALL: Role[] = ["owner", "counter", "accountant"];

export const MODULES: ModuleLink[] = [
  {
    path: "/",
    label: "Today",
    shortcut: "1",
    roles: ALL,
    purpose: "Stock, dues and today's sales at a glance.",
  },
  {
    path: "/sales",
    label: "Sales bills",
    shortcut: "2",
    roles: ALL,
    milestone: 6,
    purpose: "Create GST invoices, with pending balance and remaining stock on the bill.",
  },
  {
    path: "/purchases",
    label: "Purchases",
    shortcut: "3",
    roles: ALL,
    milestone: 4,
    purpose: "Enter supplier bills with unloading, weighbridge and transport charges.",
  },
  {
    path: "/stock",
    label: "Stock",
    shortcut: "4",
    roles: ALL,
    milestone: 4,
    purpose: "Quantity per shop and godown, transfers and physical counts.",
  },
  {
    path: "/parties",
    label: "Customers and suppliers",
    shortcut: "5",
    roles: ALL,
    milestone: 2,
    purpose: "Customers, their sites, credit limits and suppliers.",
  },
  {
    path: "/items",
    label: "Items",
    shortcut: "0",
    roles: ALL,
    milestone: 2,
    purpose: "Item master: HSN, GST, units and conversions. Import from Excel.",
  },
  {
    path: "/payments",
    label: "Payments",
    shortcut: "6",
    roles: ALL,
    milestone: 7,
    purpose: "Cash, UPI and bank receipts, allocated to bills.",
  },
  {
    path: "/rates",
    label: "Daily rates",
    shortcut: "7",
    roles: ["owner"],
    milestone: 5,
    purpose: "Today's market rate per item, customer rates and margins.",
  },
  {
    path: "/reports",
    label: "Reports",
    shortcut: "8",
    roles: ["owner", "accountant"],
    milestone: 12,
    purpose: "Daily closing, dues, GSTR-1 and 3B data.",
  },
  {
    path: "/settings",
    label: "Settings",
    shortcut: "9",
    roles: ["owner"],
    purpose: "Shop details, users, shops and godown.",
  },
];

export const modulesFor = (role: Role): ModuleLink[] =>
  MODULES.filter((m) => m.roles.includes(role));
