# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Counter staff at two shops billing steel, cement, pipes and wire quickly on a shop PC; the owner,
who checks the day's figures on a PC or phone; the accountant, who works on GST returns and dues.
(Source: docs/SPEC.md and the owner interview it records.)

## Product Purpose

An ERP for one construction-materials supplier (two shops and a godown): purchases with landed
cost, stock from append-only ledgers, GST tax invoices, credit and payments, e-way bills and
e-invoices, daily closing and GST returns. Success is a week of parallel running where the system
matches the paper books, then the paper book retires.

## Operating Context

Busy shop counters, often with a queue; keyboard-first billing (Alt shortcuts, Enter adds a
line); figures checked against the drawer at daily closing; GST month-end with an accountant.
Works offline from the cloud for fonts and assets; may run on a server inside a shop.

## Capabilities and Constraints

Roles: owner, counter, accountant; cost, margin and profit never reach counter staff. Every bill
is a real GST invoice; issued documents are never edited or deleted. Money is decimal. Single
client now, multi-tenant later.

## Brand Commitments

Visual direction pinned by the owner in October 2026 with a reference dashboard: lavender canvas,
white rounded cards, indigo-to-violet gradient, uppercase tracked labels, large bold figures, a
search bar, a bell, a gradient user card. Product name in the UI: "Construction ERP"
(assumption: no other brand name or logo has been given).

## Evidence on Hand

Real shop data does not exist in the repo; development data is seeded and must never appear as
real figures. Dashboard numbers come only from the API.

## Product Principles

1. Speed at the counter beats decoration.
2. Figures must be trustworthy and traceable to documents.
3. Each role sees only what it should.
4. Plain words: say what happens and how to recover.

## Accessibility & Inclusion

Contrast 4.5:1 for text, labels on every input, status never by colour alone, full keyboard use,
reduced motion respected. Tamil labels are planned (assumption from docs/DESIGN.md).
