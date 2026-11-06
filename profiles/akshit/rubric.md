Score each dimension from 0.0 to 1.0:

role_type — is this the right KIND of role?
  1.0 core AI/GenAI Product Manager; 0.7 adjacent product (AI Product Owner,
  Applied-AI PM, product-builder); 0.4 consultative/customer-facing solutions
  (solutions engineer / forward-deployed / solutions architect that is discovery,
  scoping, demos, solutioning, delivery — NOT writing production code or training
  models); 0.0 code-gated engineering, ML/AI engineer (training, fine-tuning,
  SFT/RLHF, MLOps), data/solution architect as the core job, IC data/research
  scientist, or non-AI/generic PM, product marketing, program/project manager.

domain — agentic AI, LLMs, RAG, agents, GenAI, enterprise AI at the core.
  1.0 agentic/LLM product at the core; partial for adjacent; small bonus if it
  rewards decision-science/experimentation/ML-product-sense or media-generation.

seniority — LEVEL and comp fit vs ~11 years / manager; money matters more than
  title to him, so a below-level or low-comp role is a real miss even if the AI
  fit is perfect.
  1.0 manager/senior/lead/staff pitched at ~8–15 yrs; 0.5 slightly off (15+ yrs
  required, or a borderline senior-IC); 0.3 clearly below his level (PM I, PM II,
  "3–5 years", mid-level); 0.1 intern/junior or Director/VP-only.

company — quality, AI-nativeness, and likely pay.
  1.0 strong-fit target; 0.8 reach target; 0.7 strong non-listed AI-native;
  0.5 safe/listed; 0.4 or less for IT-services / staffing / pure-delivery shops
  where a market-priced Salesforce-equivalent move is unlikely (even if listed);
  0.3 ordinary/unknown. (Tier hint is provided; judge AI-nativeness from the JD.)

location — 1.0 remote and India-eligible; 0.9 India on-site/hybrid; 0.5
  international remote that plausibly hires in India; 0.1 international on-site,
  US-state-locked, or US-only "remote" with no India path.

feasibility — 1.0 no blockers; lower for visa-required international with no stated
  India hiring/sponsorship, immediate/0–15-day-joiner demands (he has a notice
  period), likely-below-market comp, or a hard must-have he lacks (he does NOT
  hand-write production code or train models).

Also set these judgements (booleans):
  takeable — true if the role is India-located OR remote-and-India-eligible.
             false if it is international on-site, US-state-locked, or US-only
             "remote" with no stated India hiring or visa sponsorship. Company
             prestige does NOT make a role takeable.
  excluded_role_type — true if role_type is 0 (code-gated eng / ML-eng /
             data-architect / IC DS / non-AI or generic PM).
  unmet_must_have — true if a stated hard must-have is something he lacks; put it
             in "blocker".
  partial_jd — true if the job description looks truncated or is only a short
             snippet, so your scoring is uncertain.
