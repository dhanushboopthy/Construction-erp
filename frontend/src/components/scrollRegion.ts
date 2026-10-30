/**
 * Props for a box that scrolls sideways (a wide table on a phone). Without them a keyboard user
 * cannot reach the hidden columns; with them Tab stops on the box and the arrow keys scroll it.
 */
export const scrollRegion = (label: string) =>
  ({ role: "region", "aria-label": label, tabIndex: 0 }) as const;
