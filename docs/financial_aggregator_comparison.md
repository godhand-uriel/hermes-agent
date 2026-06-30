# Financial Aggregator Comparison

Research timestamp: 2026-06-29
Goal: choose a read-only financial aggregation provider that can feed the existing Hermes Finance Registry without becoming the dashboard source of truth.

## Recommendation

Recommended provider: Plaid.

Why:

- Strongest fit for personal finance / PFM use cases among broad providers.
- Mature read-only products for accounts, transactions, balances, investments, liabilities, income, and recurring transactions.
- Excellent sandbox/developer workflow and documentation.
- Broad institution coverage: Plaid markets 12,000+ global financial institutions for personal financial insights.
- Plaid Link provides the approved credential/consent workflow; Hermes should never collect bank credentials directly.
- It cleanly supports the required architecture: Aggregator -> Finance Registry -> Dashboard.

Important caveat: Plaid pricing is not fully public/simple. If cost for a local personal system is unacceptable after account setup, Teller is the most practical fallback because it has transparent pricing and an indie-friendly developer tier, but it has narrower overall product breadth than Plaid.

## Comparison matrix

| Provider | Cost transparency | Ease of integration | Coverage | Reliability | Security/consent | API quality | Personal finance suitability | Fit |
|---|---|---|---|---|---|---|---|---|
| Plaid | Medium: pay-as-you-go/growth/custom, no simple public per-product price | High: Link, sandbox, strong docs | High: 12,000+ institutions claimed | Good but institution-dependent; requires reauth/error handling | Strong: Link, OAuth where available, AES-256/TLS claims, user control | High | Very high | Best overall |
| MX | Low: sales/demo oriented | Medium-high: REST API, Connect Widget, SDKs | High: tens of thousands claimed; US/Canada focus | Good but throttled; dev env limited | Strong: hosted Connect, OAuth, TLS, optional JWE, IP allowlist | High | High | Enterprise alternative |
| Finicity / Mastercard Open Finance US | Low: no public simple pricing; billable/premium capabilities | Medium-high: docs, sandbox, OpenAPI/Postman/reference app | High but FI/product access can require onboarding/certification | Good; legacy connections slower; common aggregation/MFA errors | Strong: hosted Data Connect, OAuth/direct when available | High | High | Enterprise alternative |
| Teller | High: public developer and production pricing | High: simple API and Connect | Medium: 7,000+ institutions claimed | Good for supported institutions; narrower product scope | Strong: Connect, certificates/API auth | High | High for lightweight personal registry | Best fallback for cost/local simplicity |
| Envestnet/Yodlee | Low: enterprise oriented | Medium: broad but heavier | Very high: 17,000+ data sources claimed | Mature but complex | Enterprise-grade | High but heavier | High for commercial PFM | Heavyweight enterprise option |
| Akoya | Medium: self-service standard plan + enterprise custom | Medium | Medium-high for network members | Direct/consent network; coverage depends on data providers | Strong OAuth-style consent | Good | Medium-high | Good open-finance/direct-data option, less hobby-friendly |
| Stripe Financial Connections | Medium | High if already using Stripe | Medium: thousands of US institutions; US bank account focused | Good within Stripe scope | Strong Stripe consent flow | High | Medium | Use only if Stripe ecosystem is already required |

## Provider details

### 1. Plaid

Official sources:

- Link documentation: https://plaid.com/docs/link/
- Accounts API: https://plaid.com/docs/api/accounts/
- Transactions: https://plaid.com/docs/transactions/
- Balance: https://plaid.com/docs/balance/
- Investments: https://plaid.com/docs/investments/
- Liabilities: https://plaid.com/docs/liabilities/
- Income: https://plaid.com/docs/income/
- Pricing: https://plaid.com/pricing/
- Sandbox: https://plaid.com/docs/sandbox/
- Consumer security: https://plaid.com/how-it-works-for-consumers/
- Personal financial insights use case: https://plaid.com/use-cases/personal-financial-insights/

Read-only product coverage:

- Accounts: linked accounts and cached balances.
- Transactions: up to 24 months of transaction history plus ongoing updates/webhooks.
- Balance: real-time balance product when cached balances are insufficient.
- Investments: holdings, securities, and investment transactions.
- Liabilities: credit cards, student loans, mortgages, and related payment/term fields.
- Income: bank/payroll/document/consumer-report oriented income products; Bank Income can identify income streams from linked bank data.
- Recurring transactions: recurring inflow/outflow summaries as a Transactions add-on.

Security and credential handling:

- User authenticates through Plaid Link.
- OAuth institutions redirect to the institution authorization flow.
- Application stores Plaid access tokens, not bank credentials.
- Plaid says credentials are not shared with apps and that it uses AES-256/TLS and security monitoring/audits.

Reliability caveats:

- Cached balances can be stale; real-time Balance costs/latency must be considered.
- Institution connectivity can fail with `ITEM_LOGIN_REQUIRED`, `INSTITUTION_DOWN`, `INSTITUTION_NOT_RESPONDING`, `PRODUCT_NOT_READY`, rate limits, permission gaps, etc.
- Some products/add-ons require approval.

Assessment: best default provider for Hermes because it balances breadth, PFM fit, documentation, and sandbox experience.

### 2. MX

Official sources:

- Account aggregation docs: https://docs.mx.com/products/connectivity/account-aggregation/
- Account aggregation product page: https://www.mx.com/products/account-aggregation/
- Platform API overview: https://docs.mx.com/api-reference/platform-api/overview/
- Connect Widget: https://docs.mx.com/connect/

Strengths:

- Strong PFM features: 90 days of account/transaction data, cleansed transactions, categories, merchant enrichment, direct deposit/bill pay/subscription flags.
- REST API, JSON responses, Connect Widget, Web SDK, React Native SDK.
- Broad financial institution connectivity claims.
- Security features include TLS 1.2+, Basic auth with API credentials, optional JWE responses, IP whitelisting, and warnings not to expose secrets client-side.

Weaknesses:

- No simple public price list; sales-led onboarding.
- Dev environment limitations: 100 users, limited institution access, not fully representative of production.
- Aggregation throttle periods and rate limits; fields may be null.

Assessment: strong enterprise alternative, but less convenient than Plaid/Teller for a small personal local registry.

### 3. Finicity / Mastercard Open Finance US

Official sources:

- Documentation home: https://developer.mastercard.com/open-finance-us/documentation/
- Quick start: https://developer.mastercard.com/open-finance-us/documentation/quick-start-guide/index.md
- Data Connect: https://developer.mastercard.com/open-finance-us/documentation/connect/index.md
- Financial institution docs: https://developer.mastercard.com/open-finance-us/documentation/financial-institution/index.md
- Supported institutions: https://developer.mastercard.com/open-finance-us/documentation/financial-institution/supported-institutions/index.md
- Common errors: https://developer.mastercard.com/open-finance-us/documentation/errors/most-common/index.md

Strengths:

- Consumer-permissioned access for money management, payments, and lending.
- Manage/data products include account/transaction details, transaction notifications, financial statements, recurring/spend/loan-payment insights.
- Good developer assets: sandbox, test data, Postman, OpenAPI, setup scripts, SDKs, reference app.
- Hosted Data Connect handles user connection and authorization.

Weaknesses:

- No simple public pricing; some capabilities are premium/billable.
- FI/product access can depend on certification or partner onboarding.
- Legacy connections may be slower and error-prone; OAuth/direct varies by institution.

Assessment: very viable commercial alternative, but heavier than Plaid for this project's personal-registry first phase.

### 4. Teller

Official sources:

- Homepage/pricing/coverage: https://teller.io/
- Accounts API: https://teller.io/docs/api/accounts
- Transactions API: https://teller.io/docs/api/account/transactions

Strengths:

- Transparent pricing and a free developer tier with 100 live connections.
- Public pricing observed: production examples include transaction enrollment/month, balance call, identity call, and verification fees.
- Simple account, balance, identity, and transaction APIs.
- Claims 7,000+ institutions.

Weaknesses:

- Narrower product suite than Plaid for liabilities, investments, income, recurring transaction enrichment, and PFM-style categorization.
- Coverage breadth and advanced finance products are not as strong as Plaid/Yodlee/MX.

Assessment: best fallback if Plaid cost/onboarding is unacceptable, especially for personal/local use.

### 5. Envestnet/Yodlee

Official sources:

- Account aggregation: https://developer.yodlee.com/products/yodlee/account-aggregation
- Core APIs reference: https://developer.yodlee.com/products/yodlee/core-apis/docs/api-reference

Strengths:

- Enterprise-grade breadth: account aggregation product advertises 17,000+ data sources, 33M+ users, 1,400+ partners.
- Supports broad containers including banking, credit cards, investments, insurance, loans, rewards, real estate, and other assets/liabilities.

Weaknesses:

- Enterprise/commercial orientation, heavier onboarding and compliance burden.
- Pricing not simple/self-serve for a personal local registry.

Assessment: overkill unless Hermes Finance Registry becomes a commercial product with broad account-type requirements.

### 6. Akoya

Official sources:

- PFM use case: https://akoya.com/use-cases/personal-financial-management
- Getting started docs: https://docs.akoya.com/guides/getting-started
- Pricing: https://akoya.com/pricing

Strengths:

- Permissioned data access, OAuth-style flows, direct data-network approach.
- PFM use case includes balances, accounts/investments, and transactions.
- Standard self-service plan exists for lower monthly connection volumes; enterprise for larger volume.

Weaknesses:

- Network/provider coverage and access may be less straightforward than aggregator-first providers.
- Likely better for regulated production fintech than personal local use.

Assessment: strategically attractive for open-finance/direct-data compliance, but not the best first integration.

### 7. Stripe Financial Connections

Official sources:

- Docs: https://docs.stripe.com/financial-connections
- Supported institutions: https://docs.stripe.com/financial-connections/supported-institutions

Strengths:

- Permissioned access to balances, ownership, and transactions.
- Stripe lists data products including personal finance apps.
- Easy if Stripe is already part of the stack.

Weaknesses:

- US bank account focused.
- Stripe-centric; more natural for payments/account-linking than a general neutral finance registry.

Assessment: only choose if Stripe is already required for another approved system.

## Final provider decision

Use Plaid first.

Fallback decision rule:

- If Plaid production pricing/onboarding is not acceptable: use Teller for personal/local read-only account/transaction/balance ingestion.
- If the system becomes enterprise/commercial PFM: re-evaluate MX, Mastercard/Finicity, and Yodlee.
- If direct open-finance network relationships become a requirement: re-evaluate Akoya.
