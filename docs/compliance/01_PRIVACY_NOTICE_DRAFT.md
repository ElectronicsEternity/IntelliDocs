# IntelliDocs Privacy Notice - English draft

INTERNAL DRAFT, 2026-10-05. Not ready for publication. Bracketed text requires completion. Prepare and check a matching Bahasa Malaysia version before publication. The final text must describe implemented practices rather than promised controls still under development.

## Who we are

IntelliDocs is operated by PRANOVA SOLUTIONS (sole proprietorship), registration 202603163451 (AS0517057-A), at No 26 Jln SG 9/33, Taman Sri Gombak, 68100 Batu Caves, Selangor, Malaysia. For support or privacy questions and requests, contact hello.intellidocs@gmail.com. Effective date: [DATE]; version: [VERSION].

## Information we process and where it comes from

We receive account and contact details from you and our authentication service; documents, filenames and their contents from uploads; questions and conversation content from your use of IntelliDocs; and subscription/payment references and payment status from our payment provider. We also create extracted document text, hierarchy and table information, document descriptions, search representations, answers and processing-usage records.

Documents and questions may contain personal data about you or other people, including sensitive information. Only upload information you have authority to share and process. We may need to restrict certain uploads where suitable permissions or safeguards are unavailable. Your upload permission alone does not establish lawful processing of every person's information in a document.

## Why we process it

We use this information to authenticate accounts, store and extract documents, build search indexes, find relevant passages, generate answers, maintain conversations, calculate allowance usage, manage subscriptions, provide support, protect the service and investigate faults. Financial/security records may also be needed for applicable legal obligations and disputes.

Account and relevant payment details are necessary for the corresponding account/subscription features. Document and question contents are necessary for the processing you request. If you do not provide required information, we may be unable to deliver those features. [Identify any optional fields and their choices in the deployed interface.]

## Providers and overseas processing

Personal data may be transferred to and processed outside Malaysia through the following classes of providers:

| Recipient class | Information and purpose |
| --- | --- |
| Authentication, cloud storage and database providers, including Supabase and [DATABASE/HOSTING PROVIDER] | Account details, uploaded documents, extracted content and search/conversation records needed to host and operate IntelliDocs. |
| AI and embedding providers, currently OpenAI | Document content used for extraction, text used to generate search representations, and questions with selected evidence used to generate answers. Extraction can involve substantial document content; this is not a promise that only a small excerpt is sent. |
| Payment providers, currently Stripe | Account/billing references, payment and subscription information needed to process payments and manage access. Document bodies are not intended to be sent for payment processing. |
| Hosting, email and operational-support providers [IDENTIFY ACTUAL PROVIDERS] | Information needed to serve the application, deliver account messages and investigate faults. Confirm actual services before publishing. |

[Insert verified transfer destinations or a clear appropriate description, applicable transfer condition and safeguards. Do not infer processing countries from a provider's registered address or database region alone.]

Where consent is the basis for a transfer, we will present the relevant notice before requesting consent and record the choice. [This consent mechanism is not verified as implemented: do not publish this promise until it works.] Withdrawal requests may affect features that depend on the processing; explain the actual choices and consequences before consent.

Information may also be disclosed where legally required or necessary for a justified legal/security purpose, subject to applicable law. Provider contractual obligations and overseas-transfer safeguards must be established for the actual service used.

## Retention, deletion and security

Document-related caches remain while their document is maintained and are removed through the document-deletion workflow. [Implemented and tested locally on 2026-10-06; verify deployment and production permissions before publication. Saved chat answers have their own retention period.]

The Ask window displays only the current chat session. Saved questions and answers are scheduled for deletion after 14 days from each message's creation, without a separate expiry warning. Private debugging captures are scheduled for deletion after 14 days from creation. [These periods are configurable; the local implementation runs cleanup on backend startup and periodically, so outages/failures delay deletion. Confirm deployed values and operation before publication. See ../RETENTION_IMPLEMENTATION.md.] Minimal usage/cost records are separate from chat text and are not removed by this cleanup. Necessary accounting records have an agreed statutory seven-year retention period with periodic secure archiving, subject to the applicable start date and legal exceptions. [Financial archiving remains pending.] Other usage/security records: [JUSTIFIED PERIODS TO DETERMINE]. Cancellation of a subscription is separate from document deletion/account closure. Do not say all personal data expires after 14 days or that external providers follow our local period.

Copies in backups may remain until the verified backup expiry, with restricted use. Provider-held records are subject to the applicable provider arrangement and legal obligations. We do not promise immediate deletion from every backup or third-party system. [Insert verified periods/processes, account closure and deletion-request procedure.]

We use access controls and appropriate technical/organisational safeguards to protect information. [Approve this wording only after testing the production controls.] No system can guarantee absolute security. Do not claim zero provider retention or unrestricted confidentiality.

## Your choices and requests

Contact hello.intellidocs@gmail.com to request access to or correction of your personal data, exercise applicable processing/consent choices, or ask about deletion/account closure. We may verify your identity proportionately. Requests are handled subject to applicable law and lawful exceptions. [Set the response procedure and applicable deadlines; do not invent a universal deadline.]

We will update this notice when relevant practices change and identify the effective version. [Determine how material changes are communicated.]

## Internal publication and consent checks - remove from public notice

- Complete section 7 notice review and consistent Bahasa Malaysia translation; the draft is not the finished bilingual notice.
- Establish our controller/processor roles, sensitive-data approach, transfer destinations and section 129 condition.
- If relying on consent, record user/person reference, purpose/scope, notice version and hash, presented time, affirmative choice and time, and withdrawal history. Record the evidence needed without unnecessary device data. No pre-ticked consent or assumption that general terms acceptance covers all purposes.
- For third-party data inside documents, assess the uploader's role/authority and required arrangements; uploader consent is not necessarily consent from every affected person.
- Test notice presentation before collection/transfer consent, and withdrawal/deletion handling. These records/features were not implemented in this documentation task.
- Local document-cache and associated debugging-capture deletion was implemented and tested on 2026-10-06. Account-wide deletion, provider copies/backups and production filesystem access still need verification.

Sources: [JPDP personal-data principles](https://www.pdp.gov.my/ppdpv1/en/principles-of-personal-data-protection/), [JPDP overseas-transfer guidance](https://www.pdp.gov.my/ppdpv1/wp-content/uploads/2025/08/GP_CBPDT_EN.pdf), [privacy-notice guide](https://www.pdp.gov.my/ppdpv1/wp-content/uploads/2025/01/A-Quick-Guide-to-PRIVACY-NOTICE.pdf). The notice guide's full PDF fetch was unavailable in the preceding review; complete the section 7 check before publication.
