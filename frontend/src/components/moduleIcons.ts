import {
  Boxes,
  ChartColumn,
  HandCoins,
  Package,
  Receipt,
  Settings,
  ShoppingCart,
  Sun,
  Tag,
  Truck,
  Users,
  Wallet,
  type LucideIcon,
} from "lucide-react";

/** One icon per module path (modules.ts stays data-only). */
export const MODULE_ICONS: Record<string, LucideIcon> = {
  "/": Sun,
  "/sales": Receipt,
  "/purchases": ShoppingCart,
  "/stock": Boxes,
  "/parties": Users,
  "/items": Package,
  "/payments": Wallet,
  "/cash": HandCoins,
  "/rates": Tag,
  "/transport": Truck,
  "/reports": ChartColumn,
  "/settings": Settings,
};

export const iconFor = (path: string): LucideIcon => MODULE_ICONS[path] ?? Package;
