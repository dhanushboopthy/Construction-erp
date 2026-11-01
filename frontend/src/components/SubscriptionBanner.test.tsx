import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { createQueryClient } from "@/api/queryClient";
import { ApiError } from "@/api/client";
import { toFormError } from "@/api/errors";
import { App } from "@/App";
import { ReadOnlyContext } from "@/auth/ReadOnlyContext";
import { mockApi, OWNER, session } from "@/test/mockApi";

import { Button } from "./Button";
import { SubscriptionBanner } from "./SubscriptionBanner";

const base = { slug: "acme", status: "active" as const, name: "Acme", tagline: "t" };

describe("SubscriptionBanner", () => {
  it("says nothing when there is plenty of time", () => {
    const { container } = render(
      <SubscriptionBanner
        tenant={{
          ...base,
          access_state: "full",
          expires_at: "2026-12-30T18:29:59Z",
          days_left: 40,
        }}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("says nothing for a company the server sends no subscription for", () => {
    const { container } = render(<SubscriptionBanner tenant={base} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("warns from 7 days before the end", () => {
    render(
      <SubscriptionBanner
        tenant={{ ...base, access_state: "full", expires_at: "2026-11-12T10:00:00Z", days_left: 7 }}
      />,
    );
    expect(screen.getByRole("status")).toHaveTextContent(
      "Your Duolink plan ends on 12 Nov 2026. Contact Duolink to renew.",
    );
  });

  it("says the company is read-only after the end", () => {
    render(
      <SubscriptionBanner
        tenant={{
          ...base,
          access_state: "read_only",
          expires_at: "2026-11-12T10:00:00Z",
          days_left: -3,
        }}
      />,
    );
    expect(screen.getByRole("status")).toHaveTextContent(/ended on 12 Nov 2026/);
    expect(screen.getByRole("status")).toHaveTextContent(/cannot save changes/);
  });
});

describe("Button when the plan has ended", () => {
  it("turns off submit and primary buttons, with the reason, and leaves the rest", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    render(
      <ReadOnlyContext value={true}>
        <Button variant="primary" onClick={onSave}>
          Save bill
        </Button>
        <Button type="submit">Save settings</Button>
        <Button>Close</Button>
        <Button variant="primary" allowWhenReadOnly>
          Print
        </Button>
      </ReadOnlyContext>,
    );
    const save = screen.getByRole("button", { name: "Save bill" });
    expect(save).toBeDisabled();
    expect(save).toHaveAttribute("title", expect.stringMatching(/plan has ended/));
    await user.click(save);
    expect(onSave).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Save settings" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Close" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Print" })).toBeEnabled();
  });

  it("is untouched for a company with full access", () => {
    render(<Button variant="primary">Save bill</Button>);
    expect(screen.getByRole("button", { name: "Save bill" })).toBeEnabled();
  });
});

describe("SUBSCRIPTION_EXPIRED", () => {
  it("reads as one friendly sentence", () => {
    const error = new ApiError(403, {
      code: "SUBSCRIPTION_EXPIRED",
      message: "subscription expired",
      field: null,
      request_id: null,
    });
    expect(toFormError(error).message).toBe(
      "Your Duolink plan has ended, so this company is read-only. Contact Duolink to renew.",
    );
  });
});

describe("the company app when the plan has ended", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("shows the banner and turns off the save buttons", async () => {
    mockApi({
      ...session(OWNER),
      "GET /tenant": () => ({
        body: {
          ...base,
          access_state: "read_only",
          subscription_status: "expired",
          expires_at: "2026-11-12T10:00:00Z",
          days_left: -2,
        },
      }),
      "GET /stock": () => ({ body: [] }),
      "GET /eway-bills/pending": () => ({ body: [] }),
      "GET /items": () => ({ body: [] }),
    });
    window.history.pushState({}, "", "/items");
    render(<App client={createQueryClient()} />);
    expect(
      await screen.findByText(/You can look at everything but cannot save changes/),
    ).toBeVisible();
    const add = await screen.findByRole("button", { name: /Add item/i });
    expect(add).toBeDisabled();
  });
});
