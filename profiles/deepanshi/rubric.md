Score each dimension from 0.0 to 1.0:

role_type — is this a sales / revenue role where SHE owns conversions and the
  number?
  1.0 core sales / business-development / revenue leadership that owns a quota,
  pipeline and conversions (sales manager, BD manager, inside/field/regional
  sales, revenue/commercial lead, admissions/enrollment leadership with
  conversion ownership); 0.7 adjacent revenue ownership (key/enterprise account
  management, strategic partnerships, account director, quota-carrying account
  executive); 0.4 sales-adjacent with only partial number ownership (customer
  success with an upsell/renewal target, sales ops / pre-sales that still carries
  a number); 0.0 non-sales or no revenue ownership — pure marketing/brand/
  performance-marketing, product, program/project management, operations-only,
  HR/recruiting, engineering/technical, IC data/analytics, or a pure telecalling/
  BPO voice process.

domain — her core is consultative B2C selling and conversions (edtech / study-
  abroad admissions), strong on funnel optimisation and leading sales teams; she
  is open to B2B.
  1.0 the role's core is conversions / revenue ownership (B2C or B2B); partial for
  adjacent; bonus when it is in a sector she knows or named (education/edtech,
  consumer, SaaS, high-growth). Do NOT penalise B2B per se — she welcomes it — but
  a highly technical B2B sale demanding deep product/vertical expertise she lacks
  is a partial, not a 1.0.

seniority — LEVEL and comp fit vs ~9 years, Senior Manager leading a 15-person
  team; she wants to keep leading / owning a number.
  1.0 manager / senior-manager / sales-lead / AM pitched at ~7–12 yrs; 0.5 slightly
  off (AVP/Director-only or 12+ yrs required, or a strong IC quota role with no
  team); 0.3 clearly below her level (executive/associate, 2–4 yrs, management
  trainee); 0.1 intern/junior.

company — quality, growth and likely pay.
  1.0 strong-fit target; 0.8 reach target; 0.7 strong non-listed high-growth
  edtech/consumer/SaaS; 0.5 safe/listed; 0.4 or less for low-pay BPO/telecalling/
  staffing shops where a strong senior-manager comp is unlikely; 0.3 ordinary/
  unknown. (Tier hint is provided; judge growth/quality from the JD too.)

location — 1.0 remote and India-eligible; 0.9 India on-site/hybrid (Delhi NCR a
  plus, but any India city is fine); 0.5 international remote that plausibly hires
  in India; 0.1 international on-site, or "remote" locked to a non-India region.

feasibility — 1.0 no blockers; lower for immediate/0–15-day-joiner demands (she
  has a notice period), visa-required international with no India hiring, likely-
  below-market comp, or a hard must-have she lacks (e.g. a specific industry/
  vertical quota background the role insists on and she has no exposure to).

Also set these judgements (booleans):
  takeable — true if the role is India-located OR remote-and-India-eligible.
             false if it is international on-site or "remote" locked to a non-India
             region with no stated India hiring. Company prestige does NOT make a
             role takeable.
  excluded_role_type — true if role_type is 0 (non-sales / no revenue ownership /
             pure telecalling-BPO).
  unmet_must_have — true if a stated hard must-have is something she lacks; put it
             in "blocker".
  partial_jd — true if the job description looks truncated or is only a short
             snippet, so your scoring is uncertain.
