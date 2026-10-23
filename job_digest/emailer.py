"""Render the job digest as HTML and send it via Gmail SMTP.

Inline styles + table layout for email-client compatibility (Gmail especially).
The email summarises and links; full JDs live in the Sheet.
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
from .ranking import GROUP_LABELS, GROUP_ORDER, group_jobs

log = logging.getLogger(__name__)

TIER_COLORS = {"strong-fit": "#0a7d4f", "reach": "#8a5a0a", "safe": "#0a5c8a"}
GROUP_COLORS = {"target": "#5b4b8a", "remote": "#1a7f7a", "india": "#0a5c8a"}
DEFAULT_COLOR = "#334155"

INK = "#1f2933"
MUTED = "#6b7280"
LINE = "#e5e7eb"
PAGE_BG = "#eef1f4"
CARD_BG = "#ffffff"
FONT = ("-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif")
SERIF = "Georgia,'Times New Roman',serif"


def _esc(text: str) -> str:
    return html.escape(text or "")


def _pill(text: str, color: str) -> str:
    return (f'<span style="display:inline-block;background:{color};color:#fff;'
            f'font-size:11px;font-weight:600;letter-spacing:.3px;padding:2px 9px;'
            f'border-radius:999px;font-family:{FONT};">{_esc(text)}</span>')


def _posted(ts) -> str:
    try:
        ts = float(ts)
    except (TypeError, ValueError):
        return ""
    if not ts:
        return ""
    days = int((time.time() - ts) // 86400)
    if days <= 0:
        return "today"
    if days == 1:
        return "1 day ago"
    return f"{days} days ago"


def _card(i: int, job: Job) -> str:
    tier_color = TIER_COLORS.get(job.tier, DEFAULT_COLOR)
    meta_bits = [_esc(job.company)]
    if job.location:
        loc = _esc(job.location)
        if job.variant_count > 1:
            loc += f" (+{job.variant_count - 1} more location{'s' if job.variant_count > 2 else ''})"
        meta_bits.append(loc)
    if job.remote:
        meta_bits.append("Remote")
    posted = _posted(job.posted_ts)
    if posted:
        meta_bits.append(posted)
    if job.seniority:
        meta_bits.append(_esc(job.seniority))
    meta = " &middot; ".join(meta_bits)

    tier_tag = _pill(job.tier, tier_color) if job.tier else ""
    salary = (f'<span style="color:{MUTED};font-size:12px;"> &middot; {_esc(job.salary)}</span>'
              if job.salary else "")

    return f"""
    <tr><td style="padding:0 0 16px 0;">
      <div style="background:{CARD_BG};border:1px solid {LINE};border-left:5px solid {tier_color};
           border-radius:12px;padding:16px 18px;">
        <div style="font-family:{FONT};font-size:12px;color:{MUTED};margin-bottom:6px;">
          #{i}&nbsp; {tier_tag}
        </div>
        <a href="{_esc(job.url)}" style="font-family:{FONT};font-size:17px;font-weight:700;
           color:{INK};text-decoration:none;line-height:1.35;">{_esc(job.title)}</a>
        <div style="font-family:{FONT};font-size:12px;color:{MUTED};margin:6px 0 10px;">{meta}{salary}</div>
        <div style="font-family:{SERIF};font-size:14px;line-height:1.55;color:{INK};">{_esc(job.summary)}</div>
        <div style="margin-top:10px;">
          <a href="{_esc(job.url)}" style="font-family:{FONT};font-size:13px;font-weight:600;
             color:{tier_color};text-decoration:none;">Apply &rarr;</a>
        </div>
      </div>
    </td></tr>"""


def _group_section(group: str, jobs: list[Job], start_index: int) -> tuple[str, int]:
    if not jobs:
        return "", start_index
    color = GROUP_COLORS.get(group, DEFAULT_COLOR)
    cards = ""
    idx = start_index
    for job in jobs:
        cards += _card(idx, job)
        idx += 1
    header = f"""
    <tr><td style="padding:10px 0 12px 0;">
      <div style="font-family:{FONT};font-size:13px;font-weight:700;letter-spacing:.5px;
           text-transform:uppercase;color:{color};border-bottom:2px solid {color};
           padding-bottom:6px;">{_esc(GROUP_LABELS[group])} &nbsp;({len(jobs)})</div>
    </td></tr>"""
    return header + cards, idx


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
        summary = ", ".join(f"{k}: {v}" for k, v in counts.items())
        lines.append(f"Run counts — found {counts.get('_found', '?')} · "
                     f"new {counts.get('_new', '?')} · sent {counts.get('_sent', '?')}.")
        lines.append(f"Raw per source — {summary}")
    if notes:
        lines.append("Sources skipped this run: " + "; ".join(_esc(n) for n in notes))
    lines.append(f'Full JDs, filters and history live in your '
                 f'<a href="{sheet_url()}" style="color:#0a5c8a;">Google Sheet</a>.')
    joined = "<br>".join(lines)
    return f"""
    <tr><td style="padding:14px 8px 0;font-family:{FONT};font-size:11px;color:{MUTED};
        line-height:1.6;text-align:center;">{joined}</td></tr>"""


def render_html(selected: list[Job], analysis: str, notes: list[str], counts: dict) -> str:
    date_str = time.strftime("%A, %d %B %Y")
    groups = group_jobs(selected)
    sections = ""
    idx = 1
    for g in GROUP_ORDER:
        block, idx = _group_section(g, groups[g], idx)
        sections += block
    if not selected:
        sections = (f'<tr><td style="font-family:{FONT};color:{MUTED};padding:20px;">'
                    f'No new roles matched the filters this run.</td></tr>')

    return f"""<!-- AI PM Job Digest -->
<div style="background:{PAGE_BG};margin:0;padding:24px 12px;font-family:{FONT};">
  <table role="presentation" align="center" width="660" cellpadding="0" cellspacing="0"
         border="0" style="max-width:660px;width:100%;margin:0 auto;">

    <tr><td style="background:linear-gradient(135deg,#5b4b8a,#1a7f7a);background-color:#5b4b8a;
        border-radius:14px 14px 0 0;padding:24px 26px 20px;">
      <div style="font-family:{FONT};font-size:12px;letter-spacing:2px;text-transform:uppercase;
           color:#d7d0ea;font-weight:600;">AI PM Job Digest &middot; India</div>
      <div style="font-family:{SERIF};font-size:25px;color:#fff;font-weight:700;margin-top:6px;">
        {len(selected)} curated {'role' if len(selected)==1 else 'roles'} to look at</div>
      <div style="font-family:{FONT};font-size:13px;color:#e4dcf2;margin-top:8px;">{date_str}</div>
    </td></tr>

    <tr><td style="background:#fff;border-left:1px solid {LINE};border-right:1px solid {LINE};
        border-bottom:1px solid {LINE};border-radius:0 0 14px 14px;padding:14px 26px;
        font-family:{FONT};font-size:13px;color:{INK};">
      Grouped target-company first, then remote, then India on-site/hybrid. Each links straight
      to apply; full job descriptions are in your
      <a href="{sheet_url()}" style="color:#5b4b8a;font-weight:600;">Google Sheet</a>.
    </td></tr>

    <tr><td style="padding:16px 0 0 0;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
        {sections}
        {_analysis_block(analysis)}
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
