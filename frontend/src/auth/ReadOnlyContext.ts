import { createContext, useContext } from "react";

/** Why a save button is off when the company's Duolink plan has ended (M21). */
export const READ_ONLY_REASON =
  "Your Duolink plan has ended, so this company is read-only. Contact Duolink to renew.";

/** Why a save button is off inside a Duolink support session (M23). */
export const SUPPORT_READ_ONLY_REASON = "Read-only support session";

/**
 * True while the company's access_state is "read_only", or while a Duolink support session is
 * open. The shared Button reads it and turns off every save or submit button at once; the server
 * refuses writes as well (403 SUBSCRIPTION_EXPIRED, 403 SUPPORT_READ_ONLY), so this is a
 * courtesy, not the control.
 */
export const ReadOnlyContext = createContext(false);

/** The tooltip that says why. */
export const ReadOnlyReasonContext = createContext(READ_ONLY_REASON);

export function useReadOnly(): boolean {
  return useContext(ReadOnlyContext);
}

export function useReadOnlyReason(): string {
  return useContext(ReadOnlyReasonContext);
}
