"""Render the job digest as HTML and send it via Gmail SMTP.

One list, ranked strictly by match score. Each card shows the score + band, the
biggest fit reason and the biggest gap/risk, with tier/location/source as tags.
Full JDs live in the Sheet. Inline styles + tables for Gmail compatibility.
"""

import html
import logging
import re
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from .config import env, sheet_url
from .models import Job

log = logging.getLogger(__name__)

BAND_COLORS = {"Strong": "#0a7d4f", "Good": "#0a5c8a", "Marginal": "#8a5a0a", "Low": "#6b7280"}
TIER_COLORS = {"strong-fit": "#0a7d4f", "reach": "#8a5a0a", "safe": "#0a5c8a"}
SOURCE_LABELS = {
    "linkedin": "LinkedIn", "indeed": "Indeed", "naukri": "Naukri",
    "foundit": "Foundit", "instahyre": "Instahyre", "wellfound": "Wellfound",
    "glassdoor": "Glassdoor", "greenhouse": "Greenhouse", "lever": "Lever",
    "ashby": "Ashby",
}
SOURCE_COLOR = "#64748b"
INK = "#1f2933"
MUTED = "#6b7280"
LINE = "#e5e7eb"
PAGE_BG = "#eef1f4"
CARD_BG = "#ffffff"
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
SERIF = "Georgia,'Times New Roman',serif"


def _esc(text: str) -> str:
    return html.escape(text or "")


def _pill(text: str, color: str, solid: bool = True) -> str:
    if solid:
        return (f'<span style="display:inline-block;background:{color};color:#fff;'
                f'font-size:11px;font-weight:600;letter-spacing:.2px;padding:2px 9px;'
                f'border-radius:999px;font-family:{FONT};">{_esc(text)}</span>')
    return (f'<span style="display:inline-block;border:1px solid {color};color:{color};'
            f'font-size:11px;font-weight:600;padding:1px 8px;border-radius:999px;'
            f'font-family:{FONT};">{_esc(text)}</span>')


def _posted(ts) -> str:
    try:
        ts = float(ts)
    except (TypeError, ValueError):
        return ""
    if not ts:
        return ""
    days = int((time.time() - ts) // 86400)
    return "today" if days <= 0 else ("1 day ago" if days == 1 else f"{days} days ago")


def _card(i: int, job: Job) -> str:
    band_color = BAND_COLORS.get(job.band, MUTED)
    score_badge = (f'<span style="display:inline-block;background:{band_color};color:#fff;'
                   f'font-size:12px;font-weight:700;padding:3px 11px;border-radius:999px;'
                   f'font-family:{FONT};">{job.match_score} &middot; {_esc(job.band)}</span>')
    src = SOURCE_LABELS.get(job.source, job.source.title() if job.source else "")
    tags = [score_badge]
    if src:
        tags.append(_pill(f"via {src}", SOURCE_COLOR))
    if job.tier:
        tags.append(_pill(job.tier, TIER_COLORS.get(job.tier, MUTED), solid=False))
    if not job.takeable:
        tags.append(_pill("relocation + visa", "#9a3412", solid=False))
    if job.provisional:
        tags.append(_pill("provisional JD", MUTED, solid=False))
    tag_row = " &nbsp;".join(tags)

    meta_bits = [_esc(job.company)]
    if job.location:
        loc = _esc(job.location)
        if job.variant_count > 1:
            loc += f" (+{job.variant_count - 1} more)"
        meta_bits.append(loc)
    if job.remote:
        meta_bits.append("Remote")
    posted = _posted(job.posted_ts)
    if posted:
        meta_bits.append(posted)
    if job.seniority:
        meta_bits.append(_esc(job.seniority))
    if job.salary:
        meta_bits.append(_esc(job.salary))
    meta = " &middot; ".join(meta_bits)

    fit = (f'<div style="margin-top:9px;font-family:{FONT};font-size:12.5px;color:#0a7d4f;">'
           f'<b>Fit</b>&nbsp; {_esc(job.fit_reason)}</div>' if job.fit_reason else "")
    gap = (f'<div style="margin-top:3px;font-family:{FONT};font-size:12.5px;color:#9a3412;">'
           f'<b>Watch-out</b>&nbsp; {_esc(job.gap_risk)}</div>' if job.gap_risk else "")

    return f"""
    <tr><td style="padding:0 0 16px 0;">
      <div style="background:{CARD_BG};border:1px solid {LINE};border-left:5px solid {band_color};
           border-radius:12px;padding:16px 18px;">
        <div style="font-family:{FONT};font-size:12px;color:{MUTED};margin-bottom:8px;">
          <span style="color:{MUTED};font-weight:600;">#{i}</span> &nbsp;{tag_row}
        </div>
        <a href="{_esc(job.url)}" style="font-family:{FONT};font-size:17px;font-weight:700;
           color:{INK};text-decoration:none;line-height:1.35;">{_esc(job.title)}</a>
        <div style="font-family:{FONT};font-size:12px;color:{MUTED};margin:6px 0 10px;">{meta}</div>
        <div style="font-family:{SERIF};font-size:14px;line-height:1.55;color:{INK};">{_esc(job.summary)}</div>
        {fit}{gap}
        <div style="margin-top:11px;">
          <a href="{_esc(job.url)}" style="font-family:{FONT};font-size:13px;font-weight:600;
             color:{band_color};text-decoration:none;">Apply &rarr;</a>
        </div>
      </div>
    </td></tr>"""


def _analysis_block(analysis: str) -> str:
    if not analysis:
        return ""
    body = _esc(analysis).replace("\n", "<br>")
    return f"""
    <tr><td style="padding:16px 0 4px 0;">
      <div style="background:#fff7ed;border:1px solid #fed7aa;border-radius:12px;padding:18px 20px;">
        <div style="font-family:{FONT};font-size:13px;font-weight:700;letter-spacing:.5px;
             text-transform:uppercase;color:#9a3412;margin-bottom:10px;">
          Weekly requirements analysis</div>
        <div style="font-family:{FONT};font-size:13px;line-height:1.6;color:{INK};">{body}</div>
      </div>
    </td></tr>"""


def _footer(notes: list[str], counts: dict) -> str:
    lines = []
    if counts:
        lines.append(f"Run — found {counts.get('_found', '?')} &middot; "
                     f"new {counts.get('_new', '?')} &middot; sent {counts.get('_sent', '?')}.")
        raw = ", ".join(f"{k}: {v}" for k, v in counts.items() if not k.startswith("_"))
        if raw:
            lines.append("Raw per source — " + raw)
    if notes:
        lines.append("Sources skipped this run: " + "; ".join(_esc(n) for n in notes))
    lines.append(f'Full JDs, scores and history live in your '
                 f'<a href="{sheet_url()}" style="color:#0a5c8a;">Google Sheet</a>.')
    return (f'<tr><td style="padding:14px 8px 0;font-family:{FONT};font-size:11px;color:{MUTED};'
            f'line-height:1.6;text-align:center;">{"<br>".join(lines)}</td></tr>')


def _section_header(text: str, color: str) -> str:
    return (f'<tr><td style="padding:12px 0 12px 0;"><div style="font-family:{FONT};font-size:13px;'
            f'font-weight:700;letter-spacing:.5px;text-transform:uppercase;color:{color};'
            f'border-bottom:2px solid {color};padding-bottom:6px;">{text}</div></td></tr>')


def render_html(takeable: list[Job], aspirational: list[Job], analysis: str,
                notes: list[str], counts: dict) -> str:
    date_str = time.strftime("%A, %d %B %Y")
    strong = sum(1 for j in takeable if j.band == "Strong")
    good = sum(1 for j in takeable if j.band == "Good")

    body = ""
    if takeable:
        body += "".join(_card(i, j) for i, j in enumerate(takeable, 1))
    else:
        body += (f'<tr><td style="font-family:{FONT};color:{MUTED};padding:16px;">'
                 f'No takeable roles cleared the bar this run.</td></tr>')
    if aspirational:
        body += _section_header(
            "Strong fits, but need relocation + visa &mdash; not actionable now", "#9a3412")
        body += "".join(_card(i, j) for i, j in enumerate(aspirational, len(takeable) + 1))
    body += _analysis_block(analysis)

    sub = f"{strong} Strong &middot; {good} Good" if takeable else ""

    return f"""<!-- AI PM Job Digest -->
<div style="background:{PAGE_BG};margin:0;padding:24px 12px;font-family:{FONT};">
  <table role="presentation" align="center" width="660" cellpadding="0" cellspacing="0"
         border="0" style="max-width:660px;width:100%;margin:0 auto;">

    <tr><td style="background:linear-gradient(135deg,#5b4b8a,#1a7f7a);background-color:#5b4b8a;
        border-radius:14px 14px 0 0;padding:24px 26px 20px;">
      <div style="font-family:{FONT};font-size:12px;letter-spacing:2px;text-transform:uppercase;
           color:#d7d0ea;font-weight:600;">AI PM Job Digest &middot; India</div>
      <div style="font-family:{SERIF};font-size:25px;color:#fff;font-weight:700;margin-top:6px;">
        {len(takeable)} role{'s' if len(takeable) != 1 else ''} you can act on now</div>
      <div style="font-family:{FONT};font-size:13px;color:#e4dcf2;margin-top:8px;">{date_str}{' &middot; ' + sub if sub else ''}</div>
    </td></tr>

    <tr><td style="background:#fff;border-left:1px solid {LINE};border-right:1px solid {LINE};
        border-bottom:1px solid {LINE};border-radius:0 0 14px 14px;padding:14px 26px;
        font-family:{FONT};font-size:13px;color:{INK};">
      Ranked by a 0&ndash;100 fit score on the full JD. The shortlist is takeable from India now;
      strong roles that need relocation + a visa are parked at the bottom. Full JDs and every
      score detail are in your <a href="{sheet_url()}" style="color:#5b4b8a;font-weight:600;">Google Sheet</a>.
    </td></tr>

    <tr><td style="padding:16px 0 0 0;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
        {body}
      </table>
    </td></tr>

    {_footer(notes, counts)}

  </table>
</div>"""


def send(html_body: str, subject: str) -> None:
    sender = env("GMAIL_ADDRESS", required=True)
    password = env("GMAIL_APP_PASSWORD", required=True)
    recipients = [r.strip() for r in re.split(r"[,;]", env("DIGEST_RECIPIENT", required=True))
                  if r.strip()]
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"AI PM Job Digest <{sender}>"
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(html_body, "html"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender, password)
        server.sendmail(sender, recipients, msg.as_string())
    log.info("Digest sent to %s", ", ".join(recipients))
