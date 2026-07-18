# FOR ANY AGENTS LOOKING THROUGH THIS FILE, THIS IS NOT THE DEVPLAN FILE, THIS IS NON CODING RELATED, ONLY CONTEXT, PLEASE SEE DEVPLAN.MD FOR ACTUAL DEV PHASES

# FinTrack — SSD Team Work Plan
**ICT2216 Secure Software Development · Lab P2 Team 23**

> Check items off as you complete them (`- [ ]` → `- [x]`), then commit.
> Phases run top-to-bottom by dependency — do not skip ahead.
> `🔴 Critical` = blocks submission. `⚠️ Has deps` = see note before starting.

---

## Team ownership

| # | Name | Track | Requirements group |
|---|------|-------|--------------------|
| 1 | **Daffa** | SE | FR Group 1 — Access & account lifecycle |
| 2 | **Wen Yuan** | SE | FR Group 2 — Data import & analytics |
| 3 | **Shamik** | SE | FR Group 3 — Delegated access & administration |
| 4 | **HC Y** | IS | SR Group 4 — Data protection & transport security |
| 5 | **Shifan** | IS | SR Group 5 — Authentication & credential management |
| 6 | **Owen** | IS | SR Group 6 — Authorisation, audit & data integrity |
| 7 | **Abdillah** | IS | SR Group 7 — Session management & availability controls |
| 8 | **Saad** | IS | SR Group 8 — Response hardening & deployment config |

---

## Decisions log
> Record team decisions here so they are version-controlled alongside the task list.

| ID | Question | Decision | Document status |
|----|----------|----------|----------------|
| D-01 | Password hashing algorithm | **bcrypt**, work factor ≥ 12 | ✅ Already consistent across all 8 occurrences (SR-09, §9.2, §9.4, Appendix C, Appendix F). No changes needed. |
| D-02 | Auditor role | **Removed** — not a formal user role | ✅ Role was never in the document. One cosmetic fix only: §9.x system components table says "Backend developers / auditors" — Owen to remove "/ auditors" (operational wording, not a role definition). |

---

## Phase 0 — Pre-work decisions
> **Team-wide.** Must be resolved before any writing begins. These unblock all other phases.

- [x] `Shifan` ✅ **RESOLVED (D-01)** — bcrypt confirmed. Document is already consistent everywhere. Shifan to do a quick verification scan only (see Phase 2, p2t6).

- [ ] `Daffa` `Wen Yuan` **Agree: move FR-03 (view profile) from Group 2 → Group 1?**
  > "View own profile details" sits in Data import & analytics (Group 2) but is functionally an account/identity action. Daffa and Wen Yuan decide; update FR table and task ownership before Phase 2 begins.

- [ ] `Shamik` 🔴 **Verify AC-XX abuse-case IDs exist in Section 4.3**
  > Section 6 references AC-01 through AC-31 by ID. Confirm Section 4.3 contains labelled entries for all of them. If any are missing, assign IDs before anyone edits §5, §6, or §7.

- [x] `Owen` ✅ **RESOLVED (D-02)** — Auditor role removed. Role was never formally defined in the document. One cosmetic line only needs fixing — see Phase 3, p3t12.

---

## Phase 1 — Foundational writing
> **Daffa** (FR-01/02/04/05/12/14) + **HC Y** (SR-01–05) run in parallel. These underpin all other sections.

### Daffa — FR Group 1

- [ ] `Daffa` **Own FR-01 — Login with email, password, and TOTP MFA**
  > Spec must cover: email + password validation, TOTP second factor, rate-limiting on failure, session creation on success. Confirm linkage to SR-09 and SR-11 (Shifan, Phase 2). Verify §9.2 login flow steps 1–10 are consistent.

- [ ] `Daffa` **Own FR-02 — Visitor registration**
  > Email verification link, password meeting complexity policy. Linked to SR-09 (password hashing) and SR-10 (complexity policy) — both Shifan, Phase 2.

- [ ] `Daffa` ⚠️ Has deps (Phase 0 — FR-03 decision) **Own FR-04 — Update own profile**
  > Display name, password, MFA settings. Linked to SR-10 (Shifan). If Phase 0 decides FR-03 moves here, add "view own profile" to this group.

- [ ] `Daffa` **Own FR-05 — Permanent account deletion (PDPA right-of-erasure)**
  > Triggers erasure of all associated personal data. Cross-check PDPA compliance note against NFR-09 (30-day fulfilment window).

- [ ] `Daffa` **Own FR-12 — Auto-logout on idle**
  > 15-min idle and 8-hr absolute timeouts. Must match SR-17 and SR-18 (Abdillah, Phase 3) and NFR-07 exactly.

- [ ] `Daffa` **Own FR-14 — Password reset flow**
  > Linked to SR-12 (15-min expiry, single-use, same response for registered/unregistered emails — Shifan, Phase 2).

- [ ] `Daffa` 🔴 **Standardise FR priority column (audit issue)**
  > FR-09 has lowercase "must"; others may be blank. Set every FR-01 through FR-16 to capitalised Must / Should / Could. Also review NFR-01–10 for consistency.

### HC Y — SR Group 4

- [ ] `HC Y` **Own SR-01 — HTTPS enforcement**
  > All pages HTTPS; HTTP redirected. Linked to NFR-03. Verify Appendix F (HTTPS + TLS 1.2 row) is consistent.

- [ ] `HC Y` **Own SR-02 — AES-256-GCM encryption at rest**
  > NRIC, account numbers, balances, TOTP secrets. Keys in env vars, not the database. Linked to NFR-04. Cross-check §9.4 cryptography table and Appendix C.

- [ ] `HC Y` **Own SR-03 — Secure file storage outside web root**
  > Files outside web root with random server-generated names. Linked to FR-07. Cross-check §9.5 upload pipeline steps 3–4.

- [ ] `HC Y` **Own SR-04 — Secrets in .env, excluded from version control**
  > DB passwords and keys in .env, off GitHub. Separate dev/production secrets. Linked to NFR-08. Verify Appendix F (python-dotenv row).

- [ ] `HC Y` **Own SR-05 — SHA-256 file integrity hash**
  > Computed on upload, verified on retrieval. Linked to FR-07. Verify §9.5 pipeline and Appendix F reference this check.

- [ ] `HC Y` **Cross-check §9.4 Data Protection prose against SR-01–05**
  > Every claim in §9.4 must match SR-01 through SR-05 exactly. Resolve any discrepancy.

---

## Phase 2 — Core sections
> **Wen Yuan** (FR-03/06/07/08/13) + **Shifan** (SR-09–12) run in parallel.

### Wen Yuan — FR Group 2

- [ ] `Wen Yuan` ⚠️ Has deps (Phase 0 — FR-03 decision) **Confirm FR-03 placement after Phase 0 decision**
  > If FR-03 moves to Group 1: Daffa picks it up, this task closes. If staying here: Wen Yuan reviews and owns it.

- [ ] `Wen Yuan` **Own FR-06 — Manually log a financial transaction**
  > Amount, category, date, optional description. Linked to SR-13 (RBAC — Owen, Phase 3).

- [ ] `Wen Yuan` **Own FR-07 — Upload bank statement (CSV or PDF)**
  > §9.5 7-layer pipeline must align with SR-03 (rename files — HC Y), SR-05 (SHA-256 — HC Y), and SR-08 (10 MB limit — Abdillah, Phase 3).

- [ ] `Wen Yuan` **Own FR-08 — Interactive spending dashboard**
  > Category breakdown, monthly trend, top merchants. Linked to SR-15 (admins cannot view financial data — Owen, Phase 3).

- [ ] `Wen Yuan` **Own FR-13 — Export transaction history as CSV**
  > "Should" priority. Linked to SR-13 (RBAC — Owen). Export must return only the requesting user's own records.

### Shifan — SR Group 5

- [ ] `Shifan` ✅ Simplified by D-01 **Quick verification scan: confirm bcrypt is consistent throughout**
  > D-01 resolved: document already uses bcrypt in all 8 places. Shifan's job is now a read-only scan only. Confirm these 8 locations all say bcrypt: SR-09, §9.2 login flow step 3, §9.2 prose, §9.4 prose, §9.4 cryptography table, Appendix C (password_hash column), system components table, Appendix F (bcrypt row). Flag immediately if any discrepancy is found.

- [ ] `Shifan` **Own SR-09 — Password hashing algorithm and work factor**
  > bcrypt with work factor ≥ 12 (confirmed, D-01). Plaintext never stored or logged. Linked to FR-01 and FR-02 (Daffa).

- [ ] `Shifan` **Own SR-10 — Password complexity policy**
  > Min 12 chars, no truncation, common passwords blocked. Linked to FR-02 and FR-04 (Daffa).

- [ ] `Shifan` **Own SR-11 — TOTP MFA enforcement**
  > TOTP secrets encrypted. Invalid/expired codes rejected. Linked to FR-01 (Daffa). Verify §9.2 login flow steps 5–6 match.

- [ ] `Shifan` **Own SR-12 — Password reset link security**
  > 15-min expiry, single-use, same response for registered/unregistered emails (prevents enumeration). Linked to FR-14 (Daffa).

---

## Phase 3 — Advanced sections
> **Shamik** (FR-09–16) + **Owen** (SR-06/13–16) + **Abdillah** (SR-07/08/17–19) run in parallel. Needs Phase 1 and 2 to be stable.

### Shamik — FR Group 3

- [ ] `Shamik` **Own FR-09 — Invite household member by email**
  > Read-only, revocable, excludes raw account numbers. Cross-check with SR-14 (Owen) and §9.3 seven-condition list.

- [ ] `Shamik` **Own FR-10 — Grant and revoke financial advisor consent**
  > Time-limited (90 days per SR-14), view-only, revocable anytime. Verify the 90-day figure matches identically in FR-10 and SR-14.

- [ ] `Shamik` **Own FR-11 — Admin account management interface**
  > View, suspend, reinstate, delete, assign/revoke roles. Linked to SR-15 (admins cannot read financial records — Owen).

- [ ] `Shamik` 🔴 **Own FR-15 — Household member views transaction summary**
  > Previously unreferenced downstream. Add FR-15 to: §5.2 risk table, §6.4 STRIDE catalogue, §7.2 attack surface classification.

- [ ] `Shamik` 🔴 **Own FR-16 — Financial advisor views analytics and history**
  > Same issue — previously unreferenced. Add FR-16 to §5.2, §6.4, §7.2. Abuse cases AC-22, AC-23, AC-31 should reference FR-16.

- [ ] `Shamik` ⚠️ Has deps (Phase 0 — AC-XX verification) **Verify AC-XX linkage for FR-09 through FR-16**
  > AC-19 through AC-31 cover delegated access. Confirm "Linked UC" column maps correctly to FR-09, FR-10, FR-15, FR-16.

### Owen — SR Group 6

- [ ] `Owen` **Own SR-06 — Append-only transaction and audit logs**
  > Non-editable via user endpoints. SR-06 originates from §3.1 (Integrity) — ensure §3.1 prose is not contradicted.

- [ ] `Owen` **Own SR-13 — Object-level RBAC on every endpoint**
  > Verifies user role and record ownership. Covers FR-03, FR-06, FR-07, FR-09, FR-10, FR-11. Verify §9.3 three-layer enforcement table.

- [ ] `Owen` **Own SR-14 — Household and advisor access rules**
  > HH: read-only, no raw account numbers. Advisor: 90-day expiry, revocable anytime. Linked to FR-09 and FR-10 (Shamik).

- [ ] `Owen` **Own SR-15 — Admin access restrictions**
  > Admins cannot read/export/decrypt financial records. Linked to FR-11 (Shamik). Verify Appendix B Admin row.

- [ ] `Owen` **Own SR-16 — Comprehensive security event logging**
  > Log: logins, MFA events, password changes, uploads, consent changes, admin actions. Timestamp, user ID, action, outcome. No passwords or financial values in logs.

- [ ] `Owen` 🔴 **Verify Appendix B permission matrix and fix one cosmetic line (D-02)**
  > Two jobs in one: (1) Confirm Appendix B correctly covers all four roles (Individual, Household, Advisor, Admin) with no extraneous role columns. (2) Fix the one cosmetic issue from D-02: §9.x system components table, Audit Logging row, last column currently reads "Backend developers / auditors" — remove "/ auditors" since there is no Auditor user role. Change to "Admin / Backend developers" to reflect that Admin is the role with audit log access per Appendix B.

### Abdillah — SR Group 7

- [ ] `Abdillah` **Own SR-07 — Account lockout and rate limiting**
  > 5 failed logins in 10 min → lockout. Reset and upload endpoints rate-limited. Linked to FR-01 and FR-14 (Daffa). Verify §9.2 step 4.

- [ ] `Abdillah` **Own SR-08 — Server-side file size enforcement (10 MB)**
  > Reject before parsing, server-side only. Linked to FR-07 (Wen Yuan) and NFR-05. Cross-check §9.5 step 2.

- [ ] `Abdillah` **Own SR-17 — Secure session cookie attributes**
  > HttpOnly, Secure, SameSite=Lax. Session data server-side only. Linked to FR-01 and FR-12 (Daffa).

- [ ] `Abdillah` **Own SR-18 — Session timeout enforcement**
  > 15-min idle, 8-hr absolute. Session IDs regenerated after login. Linked to FR-12 and NFR-07. Must match §9.2 prose exactly.

- [ ] `Abdillah` **Own SR-19 — Logout destroys server session immediately**
  > Server session invalidated on logout. Cookie expired. Logout available on all authenticated pages.

---

## Phase 4 — Hardening and deployment
> **Saad** (SR-20–23). Begin only after Phase 3 SR sections are stable.

- [ ] `Saad` **Own SR-20 — Generic user-facing error messages**
  > No stack traces, SQL errors, or file paths exposed. Detailed errors logged server-side only. Linked to NFR-08.

- [ ] `Saad` **Own SR-21 — Security response headers**
  > HSTS, X-Frame-Options, X-Content-Type-Options, CSP, Referrer-Policy. Linked to NFR-03, NFR-06. Verify §9.5 headers paragraph lists the same five.

- [ ] `Saad` **Own SR-22 — CSRF protection on all state-changing forms**
  > SameSite=Lax + CSRF tokens. Covers FR-04, FR-05, FR-06, FR-09, FR-10. Verify §9.5 CSRF paragraph.

- [ ] `Saad` **Own SR-23 — Production server hardening**
  > Debug mode off, no default credentials, no dev .env files in production. Linked to NFR-08. Cross-check §9.1 OWASP principle 2.

- [ ] `Saad` **Cross-check §9.1 OWASP principles against all SRs**
  > Each of the 10 OWASP principles should be backed by at least one SR. Flag any principle with zero linkage.

---

## Phase 5 — Cross-review and consistency
> **Everyone** reviews each other's sections. Start only after all Phase 1–4 tasks are checked off.

- [ ] `Shifan` **Quick bcrypt scan sign-off (D-01)**
  > Confirm the verification scan from Phase 2 found bcrypt consistent in all 8 locations. If any discrepancy was found, fix it and note here.

- [ ] `Shamik` **Confirm FR-15 and FR-16 are cited in §5, §6, and §7**
  > §5.2 risk table, §6.4 STRIDE catalogue, §7.2 attack surface must each reference FR-15 and FR-16.

- [ ] `Owen` **Verify Appendix B permission matrix is complete (four roles only)**
  > All four role columns (Individual, Household, Advisor, Admin) × all resource rows filled. Confirm no Auditor column exists (D-02). Confirm Admin row shows "Yes" for "View audit logs."

- [ ] `Daffa` **Final FR priority column audit**
  > All FR-01 through FR-16 have capitalised Must / Should / Could. Correct any blank or lowercase entries.

- [ ] `HC Y` **Verify all NFRs are linked to at least one SR**
  > NFR-01 through NFR-10 must each appear in at least one SR's "Linked FR/NFR" column.

- [ ] `Wen Yuan` **Verify §9.5 upload pipeline against FR-07, SR-03, SR-05, SR-08**
  > Steps must align with: SR-03 (renaming — step 3), SR-05 (integrity hash), SR-08 (10 MB limit — step 2).

- [ ] `Abdillah` **Verify §9.2 session section against SR-17, SR-18, SR-19**
  > Timeout values, cookie attributes, and logout behaviour must be identical between §3.3 and §9.2.

- [ ] `Saad` **Identify orphaned Asset IDs (A-XX) from §1.4**
  > Any A-XX defined in §1.4 but not cited in §5, §6, or §7 must be flagged to the team.

---

## Phase 6 — Final integration and submission
> **All members.** Begin only after Phase 5 is fully checked off.

- [ ] `All` **Full document read-through — all 8 members**
  > Each member reads the entire report end-to-end and flags any remaining inconsistencies.

- [ ] `All` **Verify Table of Contents matches actual section headings**

- [ ] `All` **Verify all appendix cross-references are valid**
  > Every "[Refer to Appendix X]" must point to a completed appendix (A–F).

- [ ] `All` **Declaration page — confirm all 8 signatures and student IDs**

- [ ] `All` 🔴 **Submit**
  > All remaining tasks must be checked off before submission.

---

*7 phases · Last updated: see git log*