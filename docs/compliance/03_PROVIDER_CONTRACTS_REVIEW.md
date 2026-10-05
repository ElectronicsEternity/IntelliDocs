# Provider contracts and processing-terms review

Internal review register, 2026-10-05. NOT a signed DPA or bespoke provider contract. Public documentation review is not proof of contract acceptance, account coverage or equivalent protection under Malaysia's Act 709. Do not mark a vendor approved solely because its website mentions GDPR or certification.

## Provider register

| Provider | Public evidence / scope | Account acceptance and suitability | Next action |
| --- | --- | --- | --- |
| Supabase | Public DPA reviewed; processing/security/subprocessor/incident/deletion provisions available | UNVERIFIED applicable version, contracting entity, account coverage and acceptance | Obtain applicable agreement/DPA and acceptance evidence; complete clause checklist and Malaysian transfer review |
| OpenAI | Official API data-controls documentation reviewed; this is operational guidance, not a signed processing agreement | UNVERIFIED applicable processing terms, entity, acceptance, subprocessors and configured retention | Obtain actual account processing terms/DPA and dated evidence; reconcile agreement with endpoints and account settings |
| Stripe | Public DPA reviewed; provider describes both processor and controller activities | UNVERIFIED account entity and applicable regional terms; global link redirected to a regional page during review | Retrieve agreement/DPA applicable to this Malaysian merchant; distinguish billing service from independent fraud/legal processing |
| PostgreSQL host | Host UNVERIFIED; not automatically a separate vendor or automatically Supabase | UNVERIFIED | Confirm host first; reuse Supabase review if it is the same service, otherwise add provider terms |
| Production hosting/email/CDN/support | Actual vendors UNVERIFIED | UNVERIFIED | Register and review before deploying or giving them customer data |

## Required clause/evidence checklist - complete for each provider

| Topic | What to examine | Evidence and status to record |
| --- | --- | --- |
| Parties and scope | Correct legal entities; service/account covered; data categories and subjects; controller/processor roles | Agreement name/version/date; acceptance method/date; coverage gaps |
| Purpose and instructions | Permitted processing, documented instructions, prohibited secondary use and training arrangements | Relevant clauses and account settings; distinguish necessary controller activities |
| Confidentiality | Staff/subprocessor confidentiality, support access restrictions | Clause reference; support-access evidence |
| Security | Appropriate technical/organisational measures; transfer and storage safeguards; assurance evidence | Security schedule and limitations; assessment of protection against Act 709 needs, not merely a certification label |
| Incidents | Notification trigger, timing, content, assistance and responsible contact | Exact commitments; whether they let IntelliDocs meet its own legal deadlines |
| Rights and deletion/return | Access/correction assistance, deletion/export, end-of-contract process, backups and lawful retention exceptions | Clause reference, process, periods and actual endpoint behavior |
| Subprocessors | List, locations/functions, change notice, objection routes and flow-down obligations | Dated list, subscriptions to notices, risk/review record |
| Cross-border processing | Permitted destinations/onward transfers, applicable safeguards and our Malaysian transfer condition | Transfer assessment and any applicable contractual clauses; a DPA is not by itself the complete assessment |
| Oversight and compliance | Audit/information rights, assistance, scope of applicable-law commitments | Available reports and contract limits; identify unmet needs |
| Breach of obligations | Remedies, responsibility for subprocessors, liability limits, suspension/termination, governing law/dispute process | Risk accepted by owner or escalation/change required |

Public-document observations are deliberately not a full clause-by-clause approval. Review the complete applicable documents, not just summaries, before signing off. Do not copy a provider's terms into an IntelliDocs DPA and present it as executed.

## Evidence record template

Provider/service/account: [NON-SECRET IDENTIFIER]
IntelliDocs contracting entity: [LEGAL ENTITY]
Provider entity and role(s): [ENTITY / ROLES]
Agreement/DPA version and source: [URL / DATED COPY]
Accepted by / date / method: [EVIDENCE]
Covered data, purpose and locations: [MAPPING ROWS]
Checklist findings: [CLAUSE REFERENCES / GAPS]
Transfer condition and safeguards: [ASSESSMENT REFERENCE]
Residual risks/remediation: [OWNER / DEADLINE]
Decision: NOT REVIEWED / NEEDS REMEDIATION / APPROVED FOR SPECIFIED SCOPE
Reviewer and next review: [NAME / DATE]

Keep executed contracts/acceptance evidence in restricted business storage, not the public policy site or a public Git repository. The application repository may contain content-free status and public sources only.

## Sources and limitations

- [Supabase public DPA](https://supabase.com/legal/customer-resources/data-processing-addendum): source for its general processing commitments. Confirm current applicable version through the account.
- [OpenAI API data controls](https://developers.openai.com/api/docs/guides/your-data): endpoint-dependent retention/training controls; not a substitute for the applicable agreement.
- [Stripe DPA](https://stripe.com/legal/dpa): public processor/controller framework. Confirm region/account applicability rather than treating the redirect as the merchant's executed terms.
- [JPDP overseas-transfer guidance](https://www.pdp.gov.my/ppdpv1/wp-content/uploads/2025/08/GP_CBPDT_EN.pdf): basis for transfer/provider safeguard review. This register does not assert that every checklist term is a statutory clause with identical required wording.
