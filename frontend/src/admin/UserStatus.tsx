import { Badge } from "./Badge";
import type { PlatformUser } from "./types";

export function UserStatus({ user }: { user: PlatformUser }) {
  if (user.removed_at) return <Badge tone="neutral">Removed</Badge>;
  if (!user.is_active) return <Badge tone="neutral">Deactivated</Badge>;
  if (user.locked) return <Badge tone="warn">Locked out</Badge>;
  if (user.must_change_password) return <Badge tone="accent">Must change password</Badge>;
  return <Badge tone="good">Active</Badge>;
}
