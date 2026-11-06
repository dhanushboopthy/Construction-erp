import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createQueryClient } from "@/api/queryClient";

import { AdminApp } from "./AdminApp";

const ADMIN = {
  id: 1,
  email: "ops@duolink.app",
  full_name: "Duolink Ops",
  mobile: null,
  role: "super_admin",
  must_change_password: false,
  last_login_at: null,
};
const SUPPORT = { ...ADMIN, id: 2, full_name: "Help Desk", role: "support" };

const COMPANY = { id: 7, slug: "acme", name: "Acme Steels" };
const PLATFORM = {
  id: 1,
  kind: "platform",
  source: "scheduled",
  company: null,
  file_name: "erp-20261106-0230.dump",
  files_name: "erp-files-20261106-0230.tar.gz",
  size_bytes: 5242880,
  sha256: "a".repeat(64),
  schema_revision: "0038",
  status: "verified",
  started_at: "2026-11-06T02:30:00Z",
  completed_at: "2026-11-06T02:31:00Z",
  protected: false,
  note: null,
  error: null,
  created_by: null,
  file_present: true,
  restore_command: "./scripts/restore.sh backups/erp-20261106-0230.dump",
};
const COMPANY_BACKUP = {
  ...PLATFORM,
  id: 2,
  kind: "company",
  source: "manual",
  company: COMPANY,
  file_name: "company-acme-20261106-100000.tar.gz",
  files_name: null,
  restore_command: null,
  started_at: "2026-11-06T10:00:00Z",
};
const SAFETY = { ...COMPANY_BACKUP, id: 3, source: "safety", protected: true };
const SUMMARY = {
  last_backup_at: "2026-11-06T10:01:00Z",
  verified_count: 3,
  failed_count: 1,
  storage_bytes: 10485760,
  next_scheduled_at: "2026-11-07T02:30:00Z",
  running_jobs: 0,
  folder_ready: true,
  folder_problem: null,
  tools: [
    { name: "pg_dump", found: true },
    { name: "pg_restore", found: true },
    { name: "tar", found: true },
  ],
  restore_command_example: "./scripts/restore.sh backups/erp-YYYYMMDD-HHMM.dump",
};
const SCHEDULE = {
  daily_time: "02:30",
  keep_daily: 30,
  keep_weekly: 8,
  keep_monthly: 12,
  updated_at: null,
  next_scheduled_at: "2026-11-07T02:30:00Z",
};
const JOB = {
  id: 9,
  kind: "restore_company",
  status: "running",
  company: COMPANY,
  backup_id: 2,
  safety_backup_id: null,
  step: "Taking a protected safety backup",
  error_code: null,
  error_message: null,
  created_at: "2026-11-06T11:00:00Z",
  started_at: "2026-11-06T11:00:01Z",
  finished_at: null,
};

type Route = (url: string, init?: RequestInit) => unknown;
type Call = { url: string; method: string; body?: string };

function stubApi(routes: [RegExp, Route][], admin: object = ADMIN) {
  const calls: Call[] = [];
  const all: [RegExp, Route][] = [
    [/\/admin\/notifications$/, () => ({ count: 0, items: [] })],
    [/\/admin\/tenants\?/, () => ({ items: [COMPANY], total: 1, limit: 200, offset: 0 })],
    [/\/backups\/summary$/, () => SUMMARY],
    [/\/backups\/schedule$/, () => SCHEDULE],
  ];
  all.unshift(...routes);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      calls.push({ url, method: init?.method ?? "GET", body: init?.body as string | undefined });
      if (url.endsWith("/admin/auth/refresh")) {
        return new Response(
          JSON.stringify({ access_token: "t", token_type: "bearer", expires_in: 1800, admin }),
          { status: 200 },
        );
      }
      const match = all.find(([pattern]) => pattern.test(url));
      if (!match) return new Response(JSON.stringify({ code: "NOT_FOUND" }), { status: 404 });
      const answer = match[1](url, init);
      if (answer instanceof Response) return answer;
      return new Response(JSON.stringify(answer), { status: 200 });
    }),
  );
  return calls;
}

function renderAt(path: string) {
  window.history.pushState({}, "", path);
  return render(<AdminApp client={createQueryClient()} />);
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("AdminApp Backups page (M25)", () => {
  it("shows the tiles, the list and the command for a platform restore", async () => {
    stubApi([[/\/admin\/backups$/, () => ({ items: [COMPANY_BACKUP, PLATFORM] })]]);
    renderAt("/admin/backups");
    expect(await screen.findByRole("heading", { name: "Backups" })).toBeInTheDocument();
    const tiles = await screen.findByLabelText("Backup summary");
    expect(within(tiles).getByText("3 verified, 1 failed")).toBeInTheDocument();
    expect(within(tiles).getByText("10.0 MB")).toBeInTheDocument();
    expect(await screen.findByText("All companies")).toBeInTheDocument();
    expect(within(screen.getByRole("table")).getByText("Acme Steels")).toBeInTheDocument();
    expect(
      screen.getByText("./scripts/restore.sh backups/erp-20261106-0230.dump"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Back up all companies" })).toBeInTheDocument();
  });

  it("says plainly when the folder or a tool is missing", async () => {
    stubApi([
      [/\/admin\/backups$/, () => ({ items: [] })],
      [
        /\/backups\/summary$/,
        () => ({
          ...SUMMARY,
          folder_ready: false,
          folder_problem: "BACKUP_DIR is not set, so backups cannot be kept.",
          tools: [{ name: "pg_dump", found: false }],
        }),
      ],
    ]);
    renderAt("/admin/backups");
    expect(await screen.findByText(/BACKUP_DIR is not set/)).toBeInTheDocument();
    expect(screen.getByText(/pg_dump/)).toBeInTheDocument();
    expect(await screen.findByText("No backups yet.")).toBeInTheDocument();
  });

  it("backs up all companies and follows the job", async () => {
    const calls = stubApi([
      [/\/backups\/jobs\/9$/, () => ({ ...JOB, kind: "backup_platform", status: "succeeded" })],
      [
        /\/admin\/backups$/,
        (_url, init) => (init?.method === "POST" ? { ...JOB, status: "queued" } : { items: [] }),
      ],
    ]);
    const user = userEvent.setup();
    renderAt("/admin/backups");
    await user.click(await screen.findByRole("button", { name: "Back up all companies" }));
    await waitFor(() =>
      expect(calls.some((c) => c.method === "POST" && /\/admin\/backups$/.test(c.url))).toBe(true),
    );
    const post = calls.find((c) => c.method === "POST" && /\/admin\/backups$/.test(c.url));
    expect(JSON.parse(post?.body ?? "{}")).toEqual({ kind: "platform" });
    expect(await screen.findByText("Done.")).toBeInTheDocument();
  });

  it("restores only after RESTORE is typed, naming the company and the backup date", async () => {
    const calls = stubApi([
      [/\/admin\/backups$/, () => ({ items: [COMPANY_BACKUP] })],
      [/\/backups\/2\/restore$/, () => ({ ...JOB, status: "queued" })],
      [/\/backups\/jobs\/9$/, () => JOB],
    ]);
    const user = userEvent.setup();
    renderAt("/admin/backups");
    await user.click(await screen.findByRole("button", { name: "Restore" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Restore a company" });
    expect(dialog).toHaveTextContent("Acme Steels");
    expect(dialog).toHaveTextContent("protected safety copy");
    await user.type(within(dialog).getByLabelText("Type RESTORE to continue"), "RESTORE");
    await user.click(within(dialog).getByRole("button", { name: "Restore Acme Steels" }));
    await waitFor(() => expect(calls.some((c) => /\/2\/restore$/.test(c.url))).toBe(true));
    const sent = calls.find((c) => /\/2\/restore$/.test(c.url));
    expect(JSON.parse(sent?.body ?? "{}")).toEqual({ company_id: 7, confirm: "RESTORE" });
    expect(await screen.findByText(/Taking a protected safety backup/)).toBeInTheDocument();
  });

  it("deletes with DELETE typed and offers no delete on a protected safety copy", async () => {
    const calls = stubApi([
      [/\/admin\/backups$/, () => ({ items: [SAFETY, COMPANY_BACKUP] })],
      [/\/admin\/backups\/2$/, () => new Response(null, { status: 204 })],
    ]);
    const user = userEvent.setup();
    renderAt("/admin/backups");
    await screen.findByText("Safety copy (protected)");
    expect(screen.getAllByRole("button", { name: "Delete" })).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: "Delete" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Delete a backup" });
    await user.type(within(dialog).getByLabelText("Type DELETE to continue"), "DELETE");
    await user.click(within(dialog).getByRole("button", { name: "Delete backup" }));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
    expect(JSON.parse(calls.find((c) => c.method === "DELETE")?.body ?? "{}")).toEqual({
      confirm: "DELETE",
    });
  });

  it("saves the schedule", async () => {
    const calls = stubApi([
      [/\/admin\/backups$/, () => ({ items: [] })],
      [/\/backups\/schedule$/, (_url, init) => (init?.method === "PUT" ? SCHEDULE : SCHEDULE)],
    ]);
    const user = userEvent.setup();
    renderAt("/admin/backups");
    const time = await screen.findByLabelText("Time of day (shop time, HH:MM)");
    await user.clear(time);
    await user.type(time, "01:15");
    await user.click(screen.getByRole("button", { name: "Save schedule" }));
    await waitFor(() => expect(calls.some((c) => c.method === "PUT")).toBe(true));
    expect(JSON.parse(calls.find((c) => c.method === "PUT")?.body ?? "{}")).toMatchObject({
      daily_time: "01:15",
      keep_daily: 30,
    });
  });

  it("downloads through the signed-in API", async () => {
    const calls = stubApi([
      [/\/admin\/backups$/, () => ({ items: [PLATFORM] })],
      [/\/backups\/1\/download/, () => new Response("dump", { status: 200 })],
    ]);
    vi.stubGlobal(
      "URL",
      Object.assign(URL, { createObjectURL: () => "blob:x", revokeObjectURL: () => {} }),
    );
    const saved = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    const user = userEvent.setup();
    renderAt("/admin/backups");
    await user.click(await screen.findByRole("button", { name: "Download" }));
    await waitFor(() =>
      expect(calls.some((c) => /\/1\/download\?part=dump/.test(c.url))).toBe(true),
    );
    await waitFor(() => expect(saved).toHaveBeenCalled());
  });

  it("shows Support the list and status but no way to change anything", async () => {
    stubApi([[/\/admin\/backups$/, () => ({ items: [COMPANY_BACKUP, PLATFORM] })]], SUPPORT);
    renderAt("/admin/backups");
    await screen.findByText("Acme Steels");
    expect(screen.queryByRole("button", { name: "Back up all companies" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Restore" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Download" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete" })).not.toBeInTheDocument();
    expect(screen.getByLabelText("Time of day (shop time, HH:MM)")).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Save schedule" })).not.toBeInTheDocument();
  });
});
