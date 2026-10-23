"""AI-PM job-search digest pipeline.

A separate, self-contained system that discovers AI / Technical Product Manager
openings across India-relevant platforms via Apify (plus ATS career pages),
de-dupes them against a Google Sheet, stores every role (full JD included) in
that Sheet, and emails a curated digest every two days.

Nothing here touches the legacy notebook at the repo root.
"""
