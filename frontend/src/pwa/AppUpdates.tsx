import { useAppGeneration } from "@/api/tenant";

import { ConnectionNotice } from "./ConnectionNotice";
import { UpdateToast } from "./UpdateToast";
import { useForcedUpdateCheck } from "./updates";

/** Inside the company app's providers (it reads GET /tenant): renders nothing. */
export function ForcedUpdateWatch() {
  useForcedUpdateCheck(useAppGeneration().data);
  return null;
}

/** The update toast and "No connection" notice, on every screen of both apps. */
export function AppUpdates() {
  return (
    <>
      <ConnectionNotice />
      <UpdateToast />
    </>
  );
}
