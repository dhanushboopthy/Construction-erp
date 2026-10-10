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
