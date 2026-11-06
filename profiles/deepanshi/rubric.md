Score each dimension from 0.0 to 1.0:

role_type — is this a SENIOR / managerial sales-and-revenue role where she owns
  high-end conversions, a number and ideally a team — NOT a role whose day-to-day
  is regularly calling/dialing students or clients?
  1.0 senior/managerial sales & revenue leadership that owns a target, pipeline
  and high-value conversions, usually leading a team (senior sales manager, sales
  lead/head, enterprise sales manager, strategic-partnerships / university-
  relations manager, regional/national sales manager, key/enterprise account
  manager at a senior level, business-development manager owning strategic deals);
  0.7 adjacent senior revenue ownership (account director, senior partnerships,
  strong quota-carrying enterprise account executive at a reputable firm);
  0.4 sales-adjacent with only partial or lower-level ownership;
  0.1–0.0 (HARD NO — set excluded_role_type) roles whose core is REGULAR
  student/client calling or dialing, tele-sales / telecalling / BPO voice, ANY
  physical / field / feet-on-street / door-to-door / retail-floor / territory
  field sales or merchandising/detailing, a junior/coordinator or individual-
  contributor desk with no team and no strategic ownership (below her level), OR
  non-sales roles (pure marketing/brand, product, program/project management,
  operations-only, HR/recruiting, technical/IC data). A "sales" title does NOT
  make it senior, and "manager" does not save a feet-on-street field role —
  judge the actual day-to-day from the JD.

domain — INDUSTRY-AGNOSTIC. Her core is high-end consultative selling, funnel/
  conversion optimisation and leading sales teams; the sector does not matter
  (education and well beyond — tech, SaaS, consumer, BFSI, consulting are all
  fine), and B2B/enterprise and B2C are both welcome.
  1.0 the role's core is conversions / revenue ownership (any industry, B2B or
  B2C); 0.6–0.8 adjacent; do NOT penalise a role for being outside education, and
  do NOT penalise B2B. A highly technical B2B sale that insists on deep product/
  engineering expertise she lacks is a partial, not a 1.0.

seniority — LEVEL vs ~9 years, Senior Manager leading a 15-person team; she wants
  to keep leading / owning a number at a senior level.
  1.0 manager / senior-manager / sales-lead / senior-AM pitched at ~7–12 yrs;
  0.5 slightly off (AVP/Director-only, 12+ yrs required, or a strong senior IC
  quota role with no team); 0.3 clearly below her level (executive/associate/
  coordinator, 2–4 yrs, management trainee); 0.1 intern/junior.

company — BRAND AND QUALITY MATTER A LOT to her: she is targeting big, reputable
  multinationals and well-known brands (e.g. Microsoft, LinkedIn, Salesforce,
  Google, Amazon), and is NOT interested in small, unknown, local or staffing-
  type employers.
  1.0 strong-fit target (global MNC / top brand); 0.8 reach target (strong
  consumer/SaaS/BFSI/consulting brand); 0.6 well-known large reputable company not
  on the list; 0.4 ordinary mid-size but real/recognisable; 0.2 or less for a
  small/unknown/local firm, a staffing / placement / manpower / recruitment-
  consultancy posting on a client's behalf, or a generic no-brand employer
  ("XYZ Systems/Manpower/Consultancy/Enterprises") — flag these as
  "small/unknown employer". Judge brand from the company name + JD.

location — 1.0 remote and India-eligible; 0.9 India on-site/hybrid (Delhi NCR a
  plus, but any India metro is fine); 0.5 international remote that plausibly hires
  in India; 0.1 international on-site, or "remote" locked to a non-India region.

feasibility — 1.0 no blockers; lower for immediate/0–15-day-joiner demands (she
  has a notice period), visa-required international with no India hiring, likely-
  below-market comp, or a hard must-have she lacks (e.g. a specific technical/
  vertical quota background the role insists on and she has no exposure to).

Also set these judgements (booleans):
  takeable — true if the role is India-located OR remote-and-India-eligible.
             false if it is international on-site or "remote" locked to a non-India
             region with no stated India hiring. Company prestige does NOT make a
             role takeable.
  excluded_role_type — HARD NO. true if role_type is ~0: regular-calling /
             telecalling-BPO, ANY physical/field/feet-on-street/door-to-door/
             retail/territory field sales or detailing, coordinator/junior IC,
             non-sales, or no revenue ownership.
  excluded_company — HARD NO. true if the employer is small, unknown, local, a
             no-brand firm, or a staffing / manpower / placement / recruitment
             consultancy posting on a client's behalf. She only wants big,
             reputable, recognisable companies — when in doubt about whether a
             company is a real recognisable brand, set this true.
  stretch — true if the LEVEL and BRAND fit but the role needs a sales motion or
             background she lacks and cannot credibly claim — above all
             enterprise B2B technology / SaaS / cloud / data-platform / deeply
             technical sales (she has B2C consultative/edtech selling, not
             enterprise-tech quota experience). Put the reason in "stretch_reason".
             These stay visible but must not read as top actionable picks.
  unmet_must_have — true if a stated hard must-have is something she lacks; put it
             in "blocker".
  partial_jd — true if the job description looks truncated or is only a short
             snippet, so your scoring is uncertain.
