# Changelog

## 1.17.0 (M23): owner-granted support access

For companies (owner only):

- **Settings, Duolink support access.** Duolink cannot look inside your company unless you let it.
  Give access for 1, 4, 24 or 72 hours, say why, optionally link one of your tickets, and choose
  whether Duolink may also see cost and margin (off by default: Duolink then sees what a counter
  user sees). The screen shows the live grant with the time left and a **Turn off now** button.
  Turning it off, or giving a new grant, ends any Duolink visit at once: the next thing Duolink
  does is refused.
- **Who came in.** A history lists each Duolink visit: who, when they entered and left, why, and
  how many pages they opened. Every visit is also in your audit log.
- **Read-only, always.** Inside, Duolink sees the screens you see but cannot save anything,
  change a user or a password, or change this setting.

For Duolink staff:

- **Company page, Access tab.** Shows whether the owner has granted access and until when. A Super
  Admin gives a reason and presses **Enter company (read-only)**; the company opens in a new tab
  under an amber "Super Admin Mode" bar: "Duolink support, read-only, viewing the company, ends
  16:40, Exit". Every save button is off ("Read-only support session"). Support accounts see the
  status but cannot enter.
- **Entering needs a live grant.** Without one the admin is told to ask the owner (409). The link
  lasts two hours at most and never longer than the grant. It works only at that company's address
  and opens for that visit only: closing the tab or reloading ends it, and the admin enters again.
- **Activity, Company access.** Every visit at every company with its request count. A visit that
  was never ended and whose window has closed is marked.
- Entering and leaving are in the admin audit log and in the company's own audit log.

Not in this version: the notifications bell for a visit left open (M24).

## 1.18.0 (M24): system health, notifications, maintenance mode, audit log

For companies:

- **"Back soon" screen.** When Duolink closes the platform for maintenance, every screen is
  replaced by "Back soon" with Duolink's message (for example "Back at 9 pm"). The page checks
  again every 30 seconds and returns to your work by itself. Nothing you saved is lost; saves
  made during maintenance are refused, not half done.

For Duolink staff (admin):

- **System health** (new System item, Alt 0): API uptime, version and Python, the database's
  answer time, size and connections, free space on the backups and files disks, the last good
  backup and the last off-site copy, and counters across every company (companies, active users,
  open sessions, audit events today, open tickets). Every admin role can read it. It never shows a
  secret or a connection string.
- **Notifications bell** in the top bar with a count. It rings for subscriptions ending within 7
  days, expired companies, trials ending, new and urgent tickets, a backup older than 26 hours, a
  disk under 20% free, and more than 10 failed admin sign-ins in 24 hours. Each item says how
  serious it is in words, and links to the screen that fixes it. It is worked out on every read.
- **Maintenance mode.** A Super Admin turns it on from System, with an optional message and a
  confirmation. While on, every company request answers 503 `MAINTENANCE`; the admin, the health
  checks and the company's name keep working. It stays on across a restart until turned off, and
  a change reaches every API process within 5 seconds. Turning it on or off is audited. A restore
  (a later milestone) has its own separate in-memory switch.
- **Audit log** (new page): three tabs, Admin actions, Company access (empty until owner-granted
  access is switched on) and Sign-ins; filters by dates, admin, company and action. A Super Admin
  exports the filtered admin actions as CSV with the same rows as the screen; each export is
  itself audited.
- **Platform settings** (read-only): the security configuration from the environment (never
  secrets), the plan lifecycle explained in plain words, and links to each control.
- **Off-site sync marker.** `scripts/offsite-sync.sh` now writes `backups/.offsite-success` after a
  verified copy, so System health can show when the last off-site copy happened.

Technical: migration 0037 (`platform_maintenance`, a one-row table with no company; three new
platform audit actions).

## 1.19.0 (M25): backup and recovery from the admin, including one company

For companies:

- **Restore from a backup.** If Duolink restores your company's data, your screens show "Back soon:
  restoring from a backup" and check again every 30 seconds. Other companies keep working.
  Afterwards everyone signs in again; entries made after the backup was made must be entered
  again. Duolink keeps a protected copy of the data as it was just before.

For Duolink staff (admin):

- **Backups page** (sidebar): tiles for the last backup, verified count, storage used and the next
  scheduled run; one list for nightly, manual, safety and uploaded backups; "Back up all
  companies" and "Back up one company"; upload a company archive; the nightly time and how many
  daily, weekly and monthly copies to keep. Support can read it; only a Super Admin changes
  anything. Long work runs as a job the page follows.
- **Back up one company** as a `.tar.gz`: that company's rows as CSV (never a filtered dump), its
  attachments, logo and closing PDFs, and a manifest with row counts and SHA-256 per file.
- **Restore one company** (type `RESTORE`): refused if the archive is for another company
  (`BACKUP_WRONG_COMPANY`) or another database version (`BACKUP_SCHEMA_MISMATCH`). A protected
  safety backup is taken first; the restore is one transaction ending with the company's integrity
  check, and any failure leaves the company exactly as it was. Audited either way.
- **Platform restore stays a command.** Each platform backup shows `./scripts/restore.sh
  backups/<file>`; the admin never runs it.
- **Download** (streamed, audited), **upload** (`.tar.gz`, 200 MB, manifest checked) and **delete**
  (type `DELETE`; protected safety copies cannot be deleted).
- **The nightly loop** now takes its time and retention from the schedule and records every run in
  the same list. The `backup` service uses the backend image (it has `pg_dump`); `./backups` is
  mounted read-write for the API; `mkdir -p backups && sudo chown 10001 backups` once.
- **Purge switch.** The ledger and issued-document triggers let a row go only in a platform
  session that also sets `app.data_purge`; the company restore is the first user.
- `pg_dump`, `pg_restore` and `tar` run through one helper: an argv list, an allow-listed absolute
  path, the password only in the environment, a timeout.

Technical: migration 0038 (`platform_backup`, `platform_backup_job`, `platform_backup_schedule`,
the redefined trigger functions, seven new platform audit actions).

## 1.20.0 (M26): document numbering and company data management

For companies:

- **No change on screen.** After Duolink deletes a company's data at its request, the number
  series of what was emptied start again from 1.

For Duolink staff (admin, Super Admin only; Support never sees either tab and gets 403 on every
route, reads included):

- **Numbering tab** on the company page: one row per shop, document type and financial year, with
  the highest number that exists (read from the documents: a cancelled bill counts, a deleted one
  does not), the configured next number and the next document written out (`S1/26-27/00025`). A
  value below the highest existing plus one is refused (409 `NUMBER_TOO_LOW`: "Bill S1/26-27/00007
  already exists. The next number must be 8 or higher."); with no documents left, 1 is accepted. A
  reason is required and the change is audited with the old and new values. A counter that is ahead
  of its documents says so and offers the value that closes the gap.
- **Data tab** on the company page: every kind of business data with its row count and what blocks
  its deletion (the real foreign keys), View (latest 25 rows, four identifying columns, never an
  amount), Delete (type `DELETE`) and a separate Danger zone to delete everything (`DELETE`, the
  company's exact name and a tick-box). Both dialogs read a fresh preview when they open. A protected
  safety backup is taken first (and the deletion is refused if it fails); the deletion is one
  transaction in catalogue order with one DELETE per table; files leave storage after the commit;
  any failure rolls back, is audited (`company_data_delete_failed`) and says nothing was removed.
- **Integrity check** accepts the gap an audited numbering change explains and a series a deletion
  reset (`document_sequence_event`, append-only).
- New audit actions: `numbering_set`, `company_data_deleted`, `company_data_deleted_all`,
  `company_data_delete_failed`.
- Migration 0039. This is the one named exception to "issued documents are never deleted" and
  "ledgers are append-only" (ADR 0013), through the purge switch of migration 0038.

## 1.16.0 (M22): support tickets

For companies:

- **Help.** A new Help item in the user menu opens your company's tickets. Raise a ticket with a
  subject, a category (sign-in, billing, GST and e-way bill, stock, printing, other), a priority
  (low, normal, high, urgent) and your message. Each ticket gets a number like T-000012.
- **Duolink's answers appear in the thread.** Messages from Duolink are signed "Duolink Support";
  you do not see which person answered. When an answer arrives that you have not opened, a dot
  shows on Help (it refreshes about once a minute). Opening the ticket clears it for everyone in
  your company.
- **Reply** on the ticket at any time. A reply to a ticket that was waiting on you, or marked
  resolved, puts it back with Duolink as open.
- **Close** a ticket you raised yourself when you no longer need it. A closed ticket takes no more
  replies; raise a new one.
- **Who sees what.** The owner and the accountant see every ticket of the company. Counter staff
  see only their own.
- **You can ask for help even when your plan has ended.** A read-only company can still raise a
  ticket, reply and close.

For Duolink staff:

- **Support page** (Alt 9) with tiles for open, in progress, waiting on the company, urgent and
  unassigned tickets, filters (status, priority, company, assigned to me or unassigned, search by
  subject, number or company), and the full thread. Reply, change the status or priority, or
  assign the ticket to yourself. A Super Admin can assign it to any active admin.
- **A message alone hands the ticket to the company** (it becomes "waiting on company"). Choose a
  status with the reply to override that. To write on a closed ticket, choose a status that
  reopens it.
- **Support accounts may reply and update tickets.** This is the one place a Support account
  writes; every other admin write still needs a Super Admin.
- **Company page, Support tab** lists that company's tickets.
- Every reply and change is in the audit log (ticket number, status change, whether a message was
  sent). The message text is not copied there.

Not in this version: the notifications bell for new and urgent tickets (M24), attachments on
tickets, and email notifications.

## 1.15.0 (M21): subscriptions, manual renewals, revenue, read-only on expiry

For Duolink staff:

- **Every company now has a subscription with an end date.** A new Subscriptions page lists them
  with plan, status, end date and days left, and filters by status, plan and "ending within N
  days". Companies that were already active got an end date one year out, marked "needs review":
  check each one and correct it.
- **Record a renewal by hand** (Super Admin): pick the plan and a price option, or a number of
  days, then the amount received, how it was paid (cash, bank, UPI, cheque), a reference and notes.
  Paying during a trial starts the paid period today. Renewing early adds the time on top of the
  current end date. Renewing after the end starts today. Month ends are handled (31 Jan plus one
  month is 28 or 29 Feb).
- **Cancel** a subscription with a reason. The company becomes read-only.
- **Payments page** lists every payment with totals received, reversed and net, filtered by date,
  method and company. A mistaken payment is corrected with **Reverse**, which adds a negative row
  and keeps the original. Reversing does not shorten the end date. Payments cannot be edited or
  deleted.
- **Dashboard** shows companies by status, revenue this month and this financial year, renewals,
  new companies, a 12-month trend, companies per plan and the next expiries.
- A payment row is your receipt record. Duolink's GST tax invoice for the subscription is raised
  in your own books, outside this ERP.

For companies:

- From 7 days before the end date a banner says "Your Duolink plan ends on ...  Contact Duolink
  to renew."
- **After the end date the company is read-only.** Everyone can still sign in, read, run reports
  and download GST exports, the Tally export and PDFs. Saving anything is refused until Duolink
  records a renewal, which works at once. An ended trial with no payment is read-only too.

## 1.14.0 (M20): plans and pricing catalogue

For Duolink staff:

- **Plans are now edited, not coded.** A new Plans page shows a card per plan: users and shops
  allowed, prices and the features it lists. A Super Admin adds a plan (with a live card preview
  beside the form), edits it, copies it, archives or restores it, and deletes one nobody is on.
  Support can look.
- **Prices** are rupees with two decimals, kept exactly as typed. A plan has one to six prices,
  each for a number of days, months or years. The three plans that existed (Trial, Basic, Pro)
  keep their limits; their prices start at 0.00 for you to fill in. Nothing is charged yet.
- Only one plan is "Popular". Archiving a plan hides it when adding a company or changing a plan;
  companies already on it keep it. A plan with companies on it cannot be deleted.
- Lowering a plan's limit switches nobody off. The owner simply cannot add past it.
- Every plan change is in Duolink's audit log.

For companies:

- Nothing changes on screen. Limits are what they were.

## 1.13.0 (M19): user support tools

For Duolink staff:

- **Find a user** by name, username or company, and filter by company, role, active, locked out or
  never signed in. The list pages 50 at a time.
- **Edit a user** (name, mobile, username, role) with a reason. The username must be free in that
  company, and the company still keeps at least one active owner.
- **Reset a password.** The temporary password is shown once, with a copy button. The person's
  sessions all end and they must choose their own password at the next sign-in.
- **See where a user is signed in** (device, address, first sign-in, last use) and end one session
  without signing them out elsewhere. Support can look but not end.
- **Remove someone who has left.** Type their username to confirm. They are switched off, signed
  out and hidden from the company's user list. The account is never deleted, so the bills they
  made still carry their name. The last active owner cannot be removed.
- Every one of these is in Duolink's audit log and in the company's own, as "Duolink: <your name>".

For companies:

- The owner's user list no longer shows people Duolink removed.
- Someone whose password Duolink reset sees "Choose a new password" first, as a new owner does.
- Signing out a device (or Duolink ending it) no longer signs the same person out of their other
  devices if the old device later tries to refresh.

## 1.12.0 (M18): company profile, onboarding and the company page

For Duolink staff:

- **Add company is one form.** Besides the company and the first owner it takes the owner's email
  and mobile, the city, the name and GSTIN printed on bills, the first shop's name and code, the
  plan, and either a trial length or "Active, no trial". It can ask the owner to choose a new
  password at first sign-in (off by default). When it is saved you see the owner's sign-in address.
- **The company page has tabs:** Overview, Users, Subscription, Usage (counts only: users, shops,
  bills in 7, 30 and 90 days, supplier bills in 30 days, attached files) and Activity.
- **Contact record:** owner, email, mobile, city, state and internal notes that the company never
  sees. The company's last activity is shown to the minute.
- **Correct a company's bill details** (legal name, GSTIN, PAN, CIN, address, state) when it cannot
  reach its own Settings. It is checked as the company's form is, needs a reason, and shows in the
  company's own audit log as done by "Duolink: <your name>".
- **Set or remove a company's logo** from its page.
- **The company list** searches by name, code, owner, email or GSTIN, filters by status, plan,
  trial state and "ending within 30 days", sorts, and pages 25 at a time.
- **Close a company** (cancel) with a reason: everyone is signed out and the data is kept. A Super
  Admin can reopen it with a reason.

For companies:

- Settings has two new optional fields, **PAN** and **CIN**. The CIN prints on the tax invoice under
  the PAN; a PAN left blank is still taken from the GSTIN.
- An owner onboarded with a temporary password sees "Choose a new password" first.

## 1.11.0 (M17): Duolink staff roles

For Duolink staff (the admin at `admin.<domain>/admin`):

- Two roles. A **Super Admin** can change things. **Support** can read every screen but changes
  nothing: the buttons are hidden, and the server refuses the request as well. Admins that
  existed before this version became Super Admins.
- New **Staff** page (Alt 5): add a member with a temporary password, change their name, mobile
  and role, deactivate or reactivate them, unlock them, sign them out, or reset their password.
  New members are Support unless you choose otherwise.
- A member with a temporary password must choose their own before anything else opens.
- The last active Super Admin cannot be demoted or deactivated, and nobody can demote or
  deactivate themselves.
- Every staff change is written in "What Duolink admins did", naming who did it and to whom.
- Your role shows beside your name.
- `create_platform_admin` has a `--role` option (Super Admin unless you say `support`).
- Decision record: [ADR 0013](docs/adr/0013-platform-admin-v2.md) sets out the plan for
  milestones 17 to 30 (plans and renewals, tickets, owner-granted support access, backups,
  data management, integrations, bill templates, installable app).

For companies: nothing changes.

## 1.10.0 (FM10): orders, lots and demand

(FM9, the cash forecast and rebate accrual, was not built: the owner does not need it. This is the
next version after 1.9.0.)

- Purchases, Purchase orders: the owner places an order with a supplier at an agreed rate; the shop
  records the goods that arrive against it (a goods receipt moves no stock, stock is added when the
  supplier's bill is entered). Counter staff see quantities only, never the rate.
- A supplier bill can be entered against an order. It is checked against the goods received and
  the order rate: beyond the tolerances in Settings (1% on quantity, 0.5% on rate) a counter user
  needs the owner's PIN ("save a bill that differs from its order"); the owner may go on. A
  cheaper rate is always fine.
- Reports, Order matches (owner): bills out of tolerance, who let them through, and the purchase
  price variance (money paid above the order rate) on every bill that has an order.
- Cement by manufacturing week: when a delivery has the week printed on the bags, key it in
  (optional). A cement sale takes the oldest week first and the bill shows which weeks it came
  from. A delivery with no week is ordered by the day it came in. Costing is unchanged.
- Stock, Lost sales: one entry each time a customer asks for something out of stock (item,
  quantity, note). The owner sees what the lost sales were worth at the market rate; counter staff
  see quantities only. Fill rate per item = supplied ÷ (supplied + asked for and not in stock).

## 1.9.0 (FM8): profitability cuts and GST health

- Reports, Profit per ton (owner): profit for a month by brand, shop, who made the bill, item or
  customer, with net sales, cost, freight, margin, share of profit, tons sold and profit per ton.
  Steel sold by weight is counted in tons; cement and other items are counted in bags or pieces
  apart, so a bag never inflates the tons. Every cut adds up to the Profit & loss gross profit
  once the stock lost is taken off. With no bills it says "Not enough data yet".
- Reports, ITC at risk (owner, accountant): input tax on supplier bills in your books that
  GSTR-2B does not show, plus bills where the supplier reported less tax than you booked, and
  the GST payable estimate for the month (the 3B figure, to date) with the 20th as the due date.
  With no GSTR-2B imported it says so instead of showing a figure.
- Fixed: Profit & loss freight counted an older bill's freight again when a credit note was
  issued for it in a later month.

## 1.8.0 (FM7): controls and exceptions

- Books lock (owner, Settings): lock the books through a date after a return is filed. A bill,
  receipt, credit or debit note, cash-book voucher, adjustment, stock count, transfer, write-off,
  rebate or supplier bill dated on or before it is refused ("PERIOD_LOCKED"). Moving the lock
  earlier, or removing it, needs a reason and is written to the audit log. A month-end checklist
  shows what needs a look first.
- Reports, Bank (owner, accountant): upload the bank's CSV (any bank, columns are found by name).
  Every line is matched to a receipt, supplier payment, deposit or withdrawal of the same amount
  and direction within a few days, a matching UPI or bank reference first. Lines with no entry,
  and entries the bank never showed (a failed or fake UPI), are listed. Matching is worked out
  when you open the page, so a late entry finds its line. Statements are permanent.
- Reports, Exceptions (owner): round-number stock adjustments, adjustments just before a stock
  count, many returns from one customer, entries dated well before they were keyed in, cash near
  the daily limit and repeated weighbridge shortages from one supplier. The limits are in
  Settings; zero switches a check off.
- Settings, Audit log (owner): who changed what and when, with filters and the before and after.
- Settings gain the bank matching days and the exception limits.

## 1.7.0 (FM6): inventory analytics and replenishment

- Stock, Analysis (owner): items to reorder now (reorder point = average daily sales x lead time
  + safety stock), days of stock, ABC class by what was sold, fast, slow or non-moving by days
  sold, and how old the stock is since its last sale or purchase. Stock not moving for over 180
  days is totalled. With under 30 days of bills it says "Not enough data yet (needs 30 days)".
- Cement by age (an estimate): oldest cement first from receipts and sales.
- Stock, Stock value (owner, accountant): stock against today's market rate; the loss when it is
  worth less than cost; gain or loss against the last purchase. The owner can write the stock
  down to market value: quantities do not change, no GST is reversed, the loss comes off the
  month's net profit.
- Stock, Weight shortages (owner, accountant): billed against the weighbridge by supplier, with
  the lines to claim.
- Lead time and safety days per item, lead time per supplier, and shop defaults in Settings.

## 1.6.0 (FM5): working capital and receivables

- Reports, Working capital (owner): days inventory outstanding, days sales outstanding, days
  payables outstanding, supplier advance days and the cash conversion cycle for any month, with
  cash tied up, working capital, inventory turnover, collection efficiency and a six-month
  trend. With too little history it says "Not enough data yet", never a made-up number. The
  Today screen shows cash tied up.
- Reports, Receivables (owner and accountant): what customers owe aged from the due date (not yet
  due, 1-15, 16-30, 31-60, over 60 days late), days late, credit used and days to pay per
  customer. The owner also sees the provision for doubtful debts.
- Bad-debt write-offs (owner only): a permanent, numbered document that clears a customer's oldest
  bills with no GST effect and comes off the month's profit. It is exported to Tally.
- Settings: the provision percentage for each overdue bucket (accountant to confirm).
- Integrity check "Cost of goods": opening stock + purchases - cost of goods sold + other moves
  must equal closing stock, for the last month and this month.
- Metrics explained (owner): every figure in the app, with its formula, meaning and an example.

## 1.5.0 (FM4): Tally export

- Reports, Tally export (owner and accountant): the day book for a date range as a Tally XML
  file. Sales, credit notes, purchases, debit notes, receipts, payments, cash-book entries
  (expenses, bank deposits and withdrawals, drawings, capital), supplier rebates and freight.
- Each file is checked against GSTR-1, GSTR-3B input tax and the dues reports before it can be
  downloaded; a file that disagrees with the books is refused.
- Ledger names for Tally (sales, purchases, each GST head, cash, bank, round off...) and the
  company name are settings the accountant confirms.
- Every export is written to the audit log.

## 1.4.0 (FM3): labelled rate overrides

- A price typed for one bill is saved as an override, not as the market rate, and needs a
  reason (Sales, New bill: "Different price" and "Reason for different price"). Without one the
  bill is refused (`OVERRIDE_REASON`). Bills are printed exactly as before.
- Every new bill line keeps the rate the system would have charged, so the rupees given away
  are exact. Bills issued before FM3 keep a blank list rate and are not changed.
- Reports, Price overrides (owner): discount leakage, price realisation, a table by person and
  every hand-priced line with its reason.

## 1.3.0 (FM2): stock adjustments and ITC to reverse

- Stock, Adjustments: breakage, rust or damage, theft, free samples, weighbridge differences
  and count corrections, each with its own permanent document and a reason on the stock
  ledger. Counter adjustments above ₹10,000 need the owner's PIN.
- The owner sees the value lost this month by reason; the P&L takes stock lost off gross
  profit.
- Reports, ITC to reverse (owner and accountant): input tax on goods lost, for GSTR-3B.
- Settings: approval limits for vouchers and adjustments, and whether unexplained shortages
  reverse ITC. Fixed: saving Settings no longer resets the cash-book approval limit.

## 1.2.0 (FM1): cash book and profit and loss

- Cash book per shop: expenses by head, cash taken to or brought from the bank, the owner's
  drawings and capital. Permanent vouchers, reversed by the owner; counter expenses above
  ₹5,000 need the owner's PIN.
- The daily closing counts every cash voucher, so a normal day closes with no difference.
- Monthly profit and loss (owner): gross profit, expenses, EBITDA, net profit, break-even sales.
- KPI catalogue (`/kpis/definitions`) with formulas and "what this means" on hover.
- Today shows net sales without GST. One shop and the godown by default; shop pickers appear
  when a second shop is added.
- Finance and inventory review (`docs/FINANCE_REVIEW.md`).

## 1.1.0: new look

- "Indigo works" design: lavender canvas, white rounded cards, indigo-to-violet gradient,
  Plus Jakarta Sans, uppercase tracked labels; light and dark mode with a toggle.
- Today is a dashboard: KPI cards that open their screens, stock levels with a reorder tip, and a
  monthly sales chart (owner and accountant).
- Search box doubles as a command palette (Ctrl+K or /); alerts bell for out-of-stock items and
  waiting e-way bills; quick actions menu; gradient user card with Sign out.

## 1.0.0 (Milestone 14): ready for go-live checks

- The database refuses to delete issued documents or change their figures (ADR 0010).
- Integrity check of the books (command line and Settings, System) and a system status page.
- Backups hold the database and the uploaded files; off-site copy script; monthly restore drill;
  restore script restores files and re-checks the books.
- Password reset from the server for a forgotten owner password.
- Every route proven to need a sign-in by a test; API answers are never cached.
- Runbook and go-live plan: training, a week of parallel running, sign-off.

## 0.14.0 (Milestone 13)

- GSTR-1 tables (B2B, B2CL, B2CS, credit notes, HSN, document series) as portal JSON and Excel.
- GSTR-3B figures with input tax from purchases and debit notes.
- GSTR-2B upload and matching against purchase bills.
- Screen: Reports, GST returns (owner and accountant).

## 0.13.0 (Milestone 12)

- Daily closing per shop: figures, cash drawer count, PDF saved date-wise to a folder or an
  S3-compatible bucket, and a lock on that shop-day until the owner reopens it.
- Today strip with real figures and stock; profit by item, customer or site (owner); dues with
  ageing; monthly sales by customer segment chart.
- Screens: Reports (Alt+8) with Daily closing, Profit, Dues, Sales by segment; Today.

## 0.12.0 (Milestone 11)

- Weight checks on purchases (billed vs received) and sales (billed vs slip): a difference above
  the setting is flagged and needs a note; shortage value shown to the owner only.
- Weighbridge slips and delivery proof kept as photos or PDFs against purchases, bills and trips.
- Supplier target schemes with progress, an 80% alert and a once-only rebate booking.
- Screens: Papers on purchase and bill views, weight note fields, Supplier schemes page.

## 0.11.0 (Milestone 10)

- E-way bills from a saved bill through a GSP (fake in development, sandbox or live by
  configuration), vehicle update, 24-hour cancel, manual-number fallback, pending list and batch.
- E-invoice (IRN and QR) for B2B bills once switched on; printed on the A4 bill.
- Screens: E-way bill and e-invoice panel on the bill view, "still without an e-way bill" notice.

## 0.10.0 (Milestone 9)

- Direct-from-supplier sales linked to their purchase line: no stock moves, profit is the sale
  less the purchase's landed cost less freight, owner-only.
- Hired vehicles and trips; freight is payable to the vehicle owner and paid through Payments.
- Warning when cash paid to one person in a day passes ₹35,000.
- Screens: Transport (Alt+T) with trips, vehicles and direct sales; supplier-purchase pick on a
  bill line; link action on the owner's bill view.

## 0.9.0 (Milestone 8)

- Credit notes for goods customers bring back: automatic inside the return window, owner PIN
  after it. GST worked out again on the returned value; stock returns at its original cost; the
  customer's balance falls against the bill.
- Debit notes for goods sent back to a supplier (owner): stock leaves at landed cost and is
  refused when already sold; what we owe the supplier falls.
- A4 PDFs for both notes; invoice lines show how much has come back.
- Screens: "Return goods" on a sales bill and "Return to supplier" on a purchase.

## 0.8.0 (Milestone 7)

- Credit control at billing: approved customers, limit, days and overdue bills; unpaid part only.
- Owner PIN approvals at the counter (credit, below-cost price, discount, back-dating): one use,
  ten minutes, full audit trail, lockout after five wrong PINs.
- Receipts from customers: oldest bill first or aimed at ticked bills; advances; cash limit;
  receipts printed on the bill when money is taken with it.
- Screens: Payments (Alt+6), "Money taken now" and the owner-approval prompt on the bill screen,
  Approval PIN setting.

## 0.7.0 (Milestone 6)

- GST sales invoices: price from rates, GST per line (CGST + SGST or IGST), round-off, B2B and B2C,
  customer site as ship-to, gapless numbers, stock and customer balance updated in one transaction.
- Pending balance and stock left printed on the bill; A4 PDF with amount in words, Original,
  Duplicate and Triplicate marks.
- Safe under concurrency: item locks stop overselling; numbers stay gapless with racing bills.
- Counter staff cannot change prices or discount; cost and profit are owner-only.
- Screens: Sales bills (Alt+2): keyboard bill entry with live totals, invoice view and print.

## 0.6.0 (Milestone 5)

- Daily market rates per item with history, customer-specific rates with periods, owner-only
  margins and a suggested rate (cost + margin), warnings below cost or minimum margin.
- Price resolution: customer rate, else latest market rate on or before the date, else blocked.
- Rates quoted per ton or bag, stored per base unit without GST; GST-inclusive quoting supported.
- Screen: Daily rates (Alt+7) with a one-sheet rate entry and a Customer rates tab.

## 0.5.0 (Milestone 4)

- Purchase entry with landed cost per base unit (charges per ton, unit, trip or flat), weighbridge
  shortage raising cost, GST kept out of cost unless the shop cannot claim it.
- Supplier payable on the party ledger; supplier payments and advances with an Idempotency-Key.
- Stock transfers (Delivery challan numbers) and physical stock counts with owner posting.
- Charge types (Settings), setting for counter-staff purchase entry (G28), live landed-cost
  preview computed by the server for the owner.
- Screens: Purchases (Alt+3) with keyboard bill entry, Stock tabs: levels, transfers, counts.

## 0.4.0 (Milestone 3)

- Append-only stock ledger and party ledger (database triggers refuse UPDATE and DELETE).
- Opening balances wizard (Settings, Opening balances): stock, what customers owe, what we owe
  suppliers; drafts first, then one confirmed post.
- Stock screen (Alt+4): quantity per place from the ledger; average cost and value for the owner
  only. Statement panel on each party with aging, per site.
- `GET /reports/dues` for receivables and payables with aging.

## 0.3.0 (Milestone 2)

- Item master: category, brand, HSN, GST rate, base unit, size, grade, theoretical weight per
  piece, unit conversions (bag ↔ ton, piece ↔ kg), owner-only warning margin.
- Customers, suppliers and customer delivery sites; credit terms are owner-only.
- Excel import with a check-first step and per-row errors; downloadable template.
- Screens: Items (Alt+0) and Customers and suppliers (Alt+5), with search, unit converter and
  site management. Counter staff see items without any margin figure.

## 0.2.0 (2026-10-09)

- Milestone 0 closed: frontend installed, lint and format fixed, `package-lock.json` committed,
  CI and the frontend Docker image use `npm ci`.
- Milestone 1 screens (owner only): Settings with Shop details (each business-rule value shows
  the spec rule it controls), Users (create, edit role, name, shops and status, reset password)
  and Shops and godown (create, edit, deactivate; code fixed once created). Keyboard: Alt+N
  new, arrows move between rows, Enter opens, Esc closes.
- Frontend API types are generated from the OpenAPI spec (`src/api/schema.d.ts`).
- Role guard on every module route; navigation strip on phones; sidebar colours are tokens.
- Settings API rejects a GSTIN whose state digits differ from the shop's state code.
- Tests: role test for every API route (110 backend tests), `app/domain` at 100% coverage
  enforced in CI, screen tests with Vitest (10 frontend tests).

## 0.1.0 (2026-10-09)

- Foundation: FastAPI backend, React + TypeScript frontend, PostgreSQL, Docker Compose (dev and
  simple production with nightly backups), CI, pre-commit, Dependabot.
- Milestone 1 API: sign-in with rotating refresh sessions and lockout, roles, users, locations,
  shop settings, audit log, gapless document numbering.
- Business rules with unit tests: money, financial year, GST split and totals, units, landed
  cost, weighted-average stock, pricing, credit, weight check, compliance thresholds.
- Docs: spec v1.1 with gap fixes G1–G27, roadmap, architecture, API, design, deployment,
  glossary, ADRs 0001–0004. Claude Code `/milestone` command and two UI skills.
