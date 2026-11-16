# Government evaluation package — Bengaluru Transit Planner 4.0

Prepared 16 November 2026 on branch `v4` (version 4.0.0-alpha.3). **Nothing in this folder has been sent to any
authority.** The application has no government approval, endorsement, partnership or certification.

| Document | Purpose | State |
|---|---|---|
| `GOVERNMENT_SUBMISSION_STATUS.md` | What is ready for which kind of review | Current |
| `GOVERNMENT_READINESS_AUDIT.md` | Every feature classified from tests and the running app | Current |
| `SECURITY_AUDIT_4_0.md` | Findings with severity, evidence, fix and retest | Current |
| `PRODUCTION_READINESS_REPORT.md` | Load, reliability and hosting facts | Current |
| `ACCESSIBILITY_AUDIT.md` | WCAG 2.1 AA scan results | Current |
| `PRIVACY_POLICY.md`, `TERMS_OF_SERVICE.md`, `DATA_RETENTION_POLICY.md` | User-facing legal drafts | Drafts for professional review |
| `DATA_SOURCE_LICENCE_REGISTER.md`, `THIRD_PARTY_SERVICES_REGISTER.md` | Data and service dependencies | Current |
| `CONTACT_AND_SUBMISSION_STRATEGY.md` | Which office, which request, what outcome | Draft; contacts to confirm by phone |
| `letters/` | Cover letter and requests to BMTC, BMRCL and DULT | Drafts; not sent |
| `PILOT_PROPOSAL.md` | A limited, measurable pilot | Draft |

### PDF and spreadsheet versions
The 15 PDF/XLSX files listed in the brief will be generated from these sources once three facts exist, because each
document must quote them: (1) the public 4.0 staging URL, (2) a release-signed APK with its SHA-256, and (3) a
real-phone test record. Generating them earlier would mean printing placeholders into formal documents.

### How the evidence was produced
`tests/audit/` holds the scripts (accessibility, security probes, load test); `pytest`, `tests/browser/` and
`pip-audit` produced the remaining results. Every number in these documents comes from those runs on 16 November 2026.
