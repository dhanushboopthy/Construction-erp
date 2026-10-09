# Go-live plan

How the shop moves from paper to the system without risking a day's business. Nothing here is
optional: each step has an owner and a sign-off. Dates are relative to **Day 0**, the first day
the system is used for real bills.

## 1. Before Day 0 (a week or more ahead)

### Decisions still needed from the owner and the accountant

These are marked *Open* in [GAP_ANALYSIS](GAP_ANALYSIS.md). The system runs with the defaults
shown, but the people named must confirm them before real bills are made.

| Item | Default in the system | Who confirms |
| --- | --- | --- |
| GST in landed cost (G1) | Excluded from cost | Accountant |
| Rates quoted with or without GST (G2) | Without GST | Owner |
| Returns within 2 days go back to stock without approval (B11) | 2 days | Owner |
| Weight difference that needs a note (G20) | 0.50% | Owner |
| Cash limit per customer per day (G14) | ₹2,00,000 (hard stop); cash freight over ₹35,000 a day warns | Accountant |
| E-way thresholds (G13) | ₹50,000 between states, ₹1,00,000 within Tamil Nadu | Accountant |
| E-invoicing (G12) | Off until turnover needs it | Accountant |
| Supplier rebate GST treatment (G29), slip weight vs billed (G30) | Owner books it by hand, bill quantity stands | Accountant / owner |
| Return/GST file layouts and thresholds (G31) | Public offline-tool formats | Accountant, on a real month |
| Who may enter purchases (G28) | Counter staff may, without seeing cost | Owner |
| GSP for e-way bills and IRN | Pretend provider in development; none in production | Owner chooses; keys in `.env` |
| Cloud storage for closing PDFs and slips | Local `files` volume | Owner chooses (S3-compatible) |
| Internet at the shops (G26) | Not decided: LAN server or small cloud server | Owner |

### Set up

1. Install on the chosen machine ([DEPLOYMENT](DEPLOYMENT.md)): `APP_ENV=production`, strong
   `JWT_SECRET`, HTTPS, seed passwords set. In production the system makes no TEST-stamped PDFs and
   refuses the pretend e-way provider.
2. Settings: shop name, **GSTIN**, state, address, bank details, invoice terms; shops and godown;
   one user per person (counter staff are linked to their own shop); each person's phone or note.
3. Owner sets the approval PIN. Set a backup off-site copy: cron for `scripts/offsite-sync.sh`.
4. Items: import the item list from Excel (Items, Import). The owner checks HSN codes, GST rates,
   units and conversions (bag to ton, kg per piece) with the accountant.
5. Parties: customers (with credit terms and sites) and suppliers (with GSTIN).
6. **Opening balances** on the day before Day 0, after the last paper bill: stock per place at
   cost, customer dues, supplier dues, cash in each drawer. Post them (Settings, Opening balances).
   They cannot be edited after posting; check the totals against the paper books first.
7. Rates: enter today's market rate for every item (Daily rates).
8. Run **`make prod-verify FULL=1`** and **`make prod-drill`**. Both must pass.

## 2. Training (half a day per group, on a test copy, never on live data)

Use a copy running with `APP_ENV=staging`: every PDF is stamped TEST. Nobody trains on the live
system.

| Group | Learn | Practise until they can do it without help |
| --- | --- | --- |
| Counter staff | Sign in; keyboard shortcuts (Alt+1 to 9, Alt+N); bills with Tab and Ctrl+Enter; take money with the bill; what to do when the system says *needs the owner*; returns; closing the day | 10 bills of mixed items; a return; a bill needing the owner's PIN; the cash count and close |
| Owner | Today screen; the PIN prompt; daily rates; purchases with charges; payments; reopening a day; Settings, System | Enter a purchase with unloading and transport; approve a discount; read the profit report |
| Accountant | Reports, GST returns; dues; reading a bill and credit note PDF | Download GSTR-1 for the training month; upload a GSTR-2B and clear a mismatch |
| Whoever looks after the server | [RUNBOOK](RUNBOOK.md) | A restore drill start to finish; one upgrade with a backup first |

Give everyone the one-page rules (below) and the owner's phone number for the first week.

### One page for counter staff

- Customer, item, quantity: the system fills the price. You never type a price or discount.
- Red message under a line: fix it or call the owner. *Needs the owner*: the owner types the PIN
  on your screen; you do not hear the PIN.
- Money taken now goes in *Money taken now*. Cash from one person over ₹2,00,000 in a day is
  refused: take UPI or bank.
- Wrong bill: do not try to change it. Return goods creates a credit note. Ask the owner.
- Every evening: Reports, count the drawer, close the day.

## 3. Parallel run: one week on paper and on the system

Day 0 to Day 6: every bill is made **on the system and on the usual paper book**. The paper book
stays the book of record until sign-off.

Every evening, two people (counter staff and owner or accountant) check:

| Check | How | Pass |
| --- | --- | --- |
| Bill count | Paper bills against *Bills* on the closing screen | Equal |
| Sales total | Paper total against *Sales total* | Equal to the rupee, or each difference explained |
| Cash | Drawer count against *Should be* | Difference is zero or explained in the note |
| Stock | Count five items on the shelf against Stock | Equal |
| Customer dues | Two customers' paper balances against their statements | Equal |
| Closing | Day is closed and the PDF opens | Yes |

Write down every difference and its cause (data entry mistake, system rule, system bug). Mistakes
in entry are training; rule differences are discussed with the owner and the accountant; a bug
stops the parallel run until it is fixed and the day is repeated.

End of the week: GSTR-1 for the week is downloaded and the accountant compares it with the paper
totals. `make prod-verify FULL=1` passes. A restore drill passes on the week's backup.

## 4. Sign-off

The owner signs when all of these are true:

- [ ] Seven days with every evening check passed (or each difference explained and closed).
- [ ] Staff made bills, returns, a purchase, a payment and a closing without help on at least
      three of the days.
- [ ] The accountant has opened the GSTR-1 export and the GST returns screen without errors and
      has confirmed the decisions in section 1.
- [ ] A restore drill passed, and the off-site copy is current (`offsite-sync.sh` says OK).
- [ ] Settings, System shows *Good* on every row; no day is waiting to be closed.
- [ ] The paper book is stopped on the date of sign-off; its last page is kept for 72 months with
      the other records (G15).

| Signed by | Role | Date |
| --- | --- | --- |
| | Owner | |
| | Accountant | |
| | Counter staff, Shop 1 | |
| | Counter staff, Shop 2 | |

## 5. After go-live

- First two weeks: the owner reads Settings, System every morning; support is on call.
- First month end: the accountant files from the system with support alongside, and compares the
  first filing with the paper-based method once.
- Review the open items in GAP_ANALYSIS and decide each one.

## 6. If it must be abandoned

Until sign-off the paper book is the record, so going back costs nothing: stop using the system,
keep the data, and fix the cause. After sign-off, restore from the last good backup is the only
route; there is no switch that makes the system forget a bill, by design (ADR 0005, 0010).
