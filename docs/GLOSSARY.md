# Glossary

| Term | Meaning here |
| --- | --- |
| GST | Goods and Services Tax. Intra-state sales carry CGST + SGST (half each); inter-state carry IGST. |
| GSTIN | 15-character GST registration number; the first two digits are the state code. |
| State code | Two-digit GST state code (Tamil Nadu = 33). |
| HSN | Harmonised System code for goods, printed per invoice line. |
| ITC | Input tax credit: GST paid on purchases, claimed back against GST collected on sales. |
| Place of supply | The state where goods are delivered; decides CGST+SGST vs IGST. |
| B2B / B2C | Sale to a GST-registered buyer (with GSTIN) / to an unregistered buyer. Both get a tax invoice. |
| Tax invoice | The GST bill. The only kind of sales bill this system issues. |
| Credit note / debit note | Documents that reduce / increase an issued invoice (returns, price corrections). |
| Delivery challan | Document for moving goods without a sale (e.g. shop → godown). |
| E-way bill | Electronic permit generated before moving goods above a value threshold; carries the vehicle number. |
| E-invoice / IRN | Invoice registered on the government portal, which returns an Invoice Reference Number and QR code; mandatory for B2B above a turnover limit. |
| GSP | GST Suvidha Provider: a licensed company whose API generates e-way bills and IRNs. |
| GSTR-1 / 3B / 2B | Monthly returns: outward supplies / summary and tax payment / auto-drafted purchase statement used to check ITC. |
| URP | "Unregistered person": used in place of a GSTIN on e-way bills. |
| Landed cost | Purchase rate plus unloading, loading, weighbridge, transport and other charges, per received unit. |
| Weighbridge | Truck scale; its slip is the proof of actual weight received or sent. |
| Godown | Warehouse. |
| TMT bar | Thermo-mechanically treated steel reinforcement bar, sold by weight in sizes like 8, 10, 12 mm. |
| Theoretical weight | Standard kg per metre or per piece for a steel size, used when selling by piece. |
| Drop-ship (bill-to/ship-to) | We bill the customer, the supplier delivers directly to the customer's site. |
| Site | A customer's construction site; separate bills and statements per site. |
| Market rate | Today's selling rate per item, entered by the owner. |
| Target scheme | Supplier rebate for buying a volume within a period. |
| FY | Financial year, April to March; `26-27` in document numbers. |
| Cash book | Vouchers for money that is not a bill or a receipt: expenses, cash taken to or from the bank, the owner's drawings and capital. |
| Voucher | One cash-book entry, numbered `S1V/26-27/00001`; reversed, never edited. |
| Net sales | Bills less credit notes, excluding GST. Bills ₹20,00,000 − returns ₹50,000 = ₹19,50,000. |
| COGS | Cost of goods sold: Σ (quantity issued × weighted-average cost at issue). |
| Gross profit | Net sales − COGS − freight on sales − stock lost. ₹19,50,000 − ₹18,60,000 − ₹20,000 = ₹70,000 (no stock lost). |
| Gross margin % | Gross profit ÷ net sales × 100. ₹70,000 ÷ ₹19,50,000 = 3.59 %. |
| OPEX | Operating expenses from the cash book, excluding interest: rent, salaries, power, loading labour, vehicle. |
| EBITDA | Gross profit − OPEX (before interest). ₹70,000 − ₹99,000 = −₹29,000. |
| Net profit | EBITDA − interest. −₹29,000 − ₹12,000 = −₹41,000. |
| Contribution | Net sales − COGS − freight − variable expenses: what sales leave to pay fixed costs. |
| Break-even sales | Fixed costs ÷ (contribution ÷ net sales). ₹1,03,000 ÷ (₹62,000 ÷ ₹19,50,000) = ₹32,39,516. |
| Expense nature | Fixed (rent, salaries), variable (loading labour), or interest; decides EBITDA and break-even. |
| Stock adjustment | Stock written up or down outside a bill, purchase or transfer, with a reason; numbered `S1A/26-27/00001`. |
| Adjustment reason | Breakage, rust or damage, theft, free sample, weighbridge loss or gain, count correction. |
| Stock lost | Adjustments out less adjustments in, at average cost, counts included. Breakage ₹760 + theft ₹15,000 + count short ₹1,140 − weighbridge gain ₹240 = ₹16,660. It reduces gross profit. |
| ITC to reverse | Input tax already claimed on goods that were lost, stolen, destroyed or given away (CGST Act s.17(5)(h)); paid back in GSTR-3B 4(B)(1). Theft ₹15,000 × 18% = ₹2,700. |
| Rate override | A price typed for one bill instead of the rate board's; saved as `override` with a reason. |
| List rate | What the system would have charged a line (customer rate, else market rate) per base unit, excluding GST; kept on every bill line from FM3. |
| Discount leakage | Rupees given away by hand: (list rate − billed rate) × quantity on override lines where positive, plus bill discounts. 1,000 kg billed ₹60 against ₹62 = ₹2,000; plus a ₹500 discount = ₹2,500. |
| Price realisation | Billed value ÷ list value × 100 on hand-priced lines. ₹60,000 ÷ ₹62,000 = 96.77 %. |
| Voucher (Tally) | One balanced double-entry record in Tally: debits equal credits. A ₹66,080 bill is Dr customer 66,080, Cr Sales 56,000, Cr Output CGST 5,040, Cr Output SGST 5,040. |
| Contra | A Tally voucher that moves money between cash and bank, e.g. ₹1,50,000 taken to the bank: Dr Bank, Cr Cash. |
| Ledger master | A ledger (account name) that must exist in Tally before a voucher can post to it; the export lists them first. |
| Day book | Every voucher in date order. The export is the day book for a date range. |
| DIO | Days inventory outstanding: average stock at cost ÷ COGS x days. ₹1.2 crore ÷ ₹1.93 crore x 30 = 18.7 days. |
| DSO | Days sales outstanding: average receivables ÷ credit sales x days. ₹45,00,000 ÷ ₹60,00,000 x 30 = 22.5 days. |
| DPO | Days payables outstanding: average payables ÷ purchases x days. ₹20,00,000 ÷ ₹1.95 crore x 30 = 3.1 days. |
| Advance days | Average supplier advances ÷ purchases x days. ₹40,00,000 ÷ ₹1.95 crore x 30 = 6.2 days. |
| Cash conversion cycle | DIO + DSO + advance days - DPO. 18.7 + 22.5 + 6.2 - 3.1 = 44.3 days. |
| Cash tied up | Stock at cost + receivables + supplier advances. ₹1.2 crore + ₹45 lakh + ₹40 lakh = ₹2.05 crore. |
| Working capital | Cash tied up less payables (cash and bank are not counted yet). ₹2.05 crore - ₹20 lakh = ₹1.85 crore. |
| Overdue (by due date) | Days past a bill's due date, not its bill date; buckets not yet due, 1-15, 16-30, 31-60, over 60. |
| Collection efficiency | Collections ÷ (opening receivables + credit sales). ₹90,000 ÷ (₹1,00,000 + ₹60,000) = 56.25 %. |
| Credit utilisation | Outstanding ÷ credit limit. ₹4,00,000 ÷ ₹5,00,000 = 80 %. |
| Provision for doubtful debts | Money set aside for bills that may never be paid: each overdue bucket x its percentage. ₹95,000 overdue in the example gives ₹23,400. A report, not booked. |
| Bad-debt write-off | Giving up on money a customer owes; a numbered owner document (`S1W/26-27/00001`) with no GST effect that reduces profit. |
| ABC class | Items ranked by the cost of what was sold in 90 days: A is the few that make most of it (until 80 % is reached), B the next 15 %, C the rest. TMT ₹1,65,000, cement ₹10,500: TMT A, cement B. |
| FSN | Fast, slow or non-moving, by how many of the last 90 days an item sold. Adjustments do not count as selling. |
| Stock age | Days since the last purchase, sale or return of an item: 0-30, 31-90, 91-180, over 180. |
| Stock cover | Days the stock will last at the recent pace: 9 t ÷ 1.2 t a day = 7.5 days. |
| Lead time | Days from ordering to delivery; per item, supplier or shop. |
| Safety stock | Days of sales kept back for a bad week: 1.2 t x 2 days = 2.4 t. |
| Reorder point | Average daily sales x lead time + safety stock: 1.2 t x 7 + 2.4 t = 10.8 t. Order when stock falls to it. |
| NRV | Net realisable value: today's market rate less the cost of selling. Stock is valued at the lower of cost and NRV (AS 2): TMT cost ₹55, market ₹54, 23,000 kg = ₹23,000 loss. |
| Holding gain or loss | (Last purchase cost - average cost) x quantity on hand. |
| Write-down | Lowering the value of stock to its NRV; a permanent document `S1N/26-27/00001`. No quantity moves, no input tax is reversed, the loss comes off net profit. |
| Cement age (FIFO proxy) | Cement by the day it came in, assuming the oldest is sold first; an estimate, not lot tracking. |
| Weight shortage | Billed weight less weighbridge weight on a supplier bill: 1,000 kg billed, 994 kg received = 0.60 %, ₹420 on ₹70,000 of goods. |
| Books lock | A date the owner sets after a return is filed: nothing can be dated on or before it until the owner reopens it with a reason. Lock through 30-09-2026 and a credit note dated 30-09 is refused. |
| Bank reconciliation | Matching the bank's statement lines to what the shop recorded. 10 lines, 8 match a receipt, 2 do not: ₹18,750 cheque deposit and ₹590 bank charges. |
| Recorded, not in the bank | A UPI or bank receipt in the books that the statement never shows: ₹8,000 receipt with reference 999999999999, no credit. A failed or fake payment until proved otherwise. |
| Exception | An entry that looks like a usual way money or stock goes missing, such as 20 kg wire at ₹50 = exactly ₹1,000 adjusted the day before a count. A reason to ask, not proof. |
| Profit per ton | Gross profit of the lines sold by weight ÷ tons sold. Brand A: ₹6,000 on 10 t = ₹600 a ton; brand B: ₹6,000 on 4 t = ₹1,500 a ton. Bags and pieces are counted apart. |
| Contribution per ton | (Net sales - cost - freight - loading and other variable expenses - stock lost) ÷ tons. (₹5,60,000 - ₹5,50,000 - ₹4,000 - ₹1,000 - ₹500) ÷ 10 t = ₹450. |
| ITC at risk | Input tax on supplier bills in the books that GSTR-2B does not show (plus the shortfall where the supplier reported less): cannot be claimed until the supplier files. ₹18,000 missing + ₹20 short = ₹18,020. |
| GST payable estimate | The GSTR-3B net payable for the month so far, due on the 20th of the next month. A minus figure is credit carried forward. |
| Purchase order | What you asked a supplier for and at what rate, numbered `S1O/26-27/00001`. 10 t TMT at ₹55,000 a ton. |
| Goods receipt (GRN) | What actually arrived against an order, numbered `S1G/26-27/00001`. It moves no stock: stock enters with the supplier's bill. 9.8 t arrived. |
| Three-way match | Checking a supplier's bill against the order and the goods received. A bill for 10 t when 9.8 t arrived is 2.04% over; with a 1% tolerance it needs the owner's PIN. |
| PPV | Purchase price variance: (rate on the bill - rate on the order) x quantity. Bill ₹55,500 against order ₹55,000 on 10 t = ₹5,000 paid over. |
| Lot (cement) | One delivery of cement, named by the manufacturing week printed on the bag. Sold oldest week first; a delivery with no week is ordered by the day it came in. |
| Lost sale | A customer asked for something you did not have. Logged in one step; the owner sees it valued at the market rate. 10 bags x ₹380.45 = ₹3,804.50. |
| Fill rate | Quantity supplied ÷ (supplied + asked for and not in stock) x 100. 90 bags sold and 10 asked for = 90%. |
