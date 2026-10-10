import { useLocations } from "@/api/setup";
import type { Location } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";

/** The shops this user works with. With one shop the screens hide shop pickers and shop
 * columns; they appear by themselves as soon as a second shop is added in Settings. */
export function useShops(): { shops: Location[]; single: boolean; loading: boolean } {
  const { user } = useAuth();
  const locations = useLocations();
  const shops = (locations.data ?? []).filter(
    (l) =>
      l.kind === "shop" &&
      l.is_active &&
      (user?.role !== "counter" || user.locations.some((u) => u.id === l.id)),
  );
  return { shops, single: shops.length <= 1, loading: locations.isLoading };
}
