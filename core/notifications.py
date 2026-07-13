"""
core.notifications
=====================
Email + SMS dispatch, ported from includes/mailer.php,
includes/sms.php and includes/notify.php.

  * Email is sent with Python's built-in smtplib/email (no external
    dependency needed — replaces PHPMailer).
  * SMS supports the same two providers as the original: Semaphore
    (Philippines) and Twilio, via plain HTTP calls with `requests`.
  * Every attempt (success or failure) is written to notification_log,
    exactly like the PHP version, so Admin -> Notifications shows full
    history either way.
"""
from __future__ import annotations

import re
import smtplib
import ssl
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from typing import Optional

import requests

from config.settings import get_settings, LOG_DIR
from core.utils import format_currency, format_date
from database.models import NotificationLog
from sqlalchemy.orm import Session


@dataclass
class SendResult:
    success: bool
    error: Optional[str] = None
    skipped: bool = False


# ─────────────────────────────────────────────────────────────────────────
#  Email
# ─────────────────────────────────────────────────────────────────────────

def email_template(title: str, body_html: str) -> str:
    """Plain, professional HTML wrapper — a business letter, not a
    themed app screenshot. White background, one muted accent color,
    no gradients or emoji badges, so it reads as legitimate payroll
    correspondence rather than a marketing email."""
    company = get_settings().mail.company_name
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>
  body {{ margin:0; padding:0; background:#eef1f5; font-family:Arial,'Segoe UI',sans-serif; }}
  .wrapper {{ max-width:560px; margin:0 auto; padding:28px 16px; }}
  .card {{ background:#ffffff; border:1px solid #dbe1e8; border-radius:6px; overflow:hidden; }}
  .header {{ padding:22px 32px; border-bottom:3px solid #1e3a5f; }}
  .header-title {{ color:#1e3a5f; font-size:1.15rem; font-weight:700; margin:0; }}
  .header-sub {{ color:#8a94a3; font-size:0.72rem; margin-top:2px; text-transform:uppercase; letter-spacing:0.06em; }}
  .body {{ padding:30px 32px; }}
  .body p {{ color:#2b3038; font-size:0.94rem; line-height:1.65; margin:0 0 14px; }}
  .highlight-box {{ background:#f4f6f9; border:1px solid #dbe1e8; border-left:3px solid #1e3a5f; border-radius:4px; padding:16px 20px; margin:18px 0; text-align:center; }}
  .highlight-code {{ font-family:'Courier New',monospace; font-size:1.7rem; font-weight:700; color:#1e3a5f; letter-spacing:0.12em; }}
  .highlight-label {{ font-size:0.68rem; color:#8a94a3; text-transform:uppercase; letter-spacing:0.08em; margin-top:4px; }}
  .status-line {{ font-size:0.85rem; font-weight:700; color:#1e3a5f; margin-bottom:10px; }}
  .footer {{ padding:16px 32px 22px; }}
  .footer p {{ color:#a7aeb8; font-size:0.68rem; margin:0; line-height:1.5; }}
</style></head>
<body><div class="wrapper"><div class="card">
  <div class="header">
    <div class="header-title">{company}</div>
    <div class="header-sub">Payroll &amp; HR Management System</div>
  </div>
  <div class="body">{body_html}</div>
  <div class="footer"><hr style="border:none;border-top:1px solid #eef1f5;margin:0 0 14px;">
    <p>This is an automated message from the {company} payroll system. Please do not reply directly
    to this email; contact your HR or Payroll office for any questions.</p>
  </div>
</div></div></body></html>"""


def send_email(to_email: str, to_name: str, subject: str, html_body: str, plain_body: str = "") -> SendResult:
    cfg = get_settings().mail
    if not cfg.enabled:
        return SendResult(False, "Email is disabled in Settings \u2192 Mail.")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = formataddr((cfg.from_name, cfg.from_email))
    msg["To"] = formataddr((to_name or to_email, to_email))
    msg["Reply-To"] = cfg.from_email

    plain = plain_body or re.sub("<[^<]+?>", "", html_body)
    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        if cfg.encryption == "ssl":
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(cfg.host, cfg.port, timeout=15, context=context) as server:
                server.login(cfg.username, cfg.password)
                server.sendmail(cfg.from_email, [to_email], msg.as_string())
        else:
            with smtplib.SMTP(cfg.host, cfg.port, timeout=15) as server:
                server.ehlo()
                if cfg.encryption == "tls":
                    context = ssl.create_default_context()
                    server.starttls(context=context)
                    server.ehlo()
                server.login(cfg.username, cfg.password)
                server.sendmail(cfg.from_email, [to_email], msg.as_string())
        return SendResult(True)
    except Exception as e:  # noqa: BLE001
        return SendResult(False, str(e))


def _company() -> str:
    return get_settings().mail.company_name


def welcome_email_html(full_name: str, username: str) -> str:
    body = f"""
    <div class="status-line">Account Activated</div>
    <p>Dear {full_name},</p>
    <p>This is to confirm that your employee account with <strong>{_company()}</strong> has been
    successfully activated. You may now sign in to the Employee Portal to view your payslips,
    attendance records, and personal information.</p>
    <div class="highlight-box">
      <div class="highlight-label">Your Login Username</div>
      <div class="highlight-code" style="font-size:1.15rem;">{username}</div>
    </div>
    <p style="font-size:0.8rem;color:#8a94a3;">For your security, please keep your login credentials
    confidential and do not share them with anyone.</p>
    <p>Sincerely,<br>{_company()} Payroll Team</p>"""
    return email_template(f"Account Activated \u2014 {_company()}", body)


def otp_email_html(name: str, otp_code: str, expiry_minutes: int) -> str:
    body = f"""
    <p>Dear {name},</p>
    <p>We received a request to reset the password for your account with <strong>{_company()}</strong>.
    Please use the one-time verification code below to proceed:</p>
    <div class="highlight-box">
      <div class="highlight-label">One-Time Password (OTP)</div>
      <div class="highlight-code">{otp_code}</div>
      <div class="highlight-label" style="margin-top:8px;">This code is valid for {expiry_minutes} minutes</div>
    </div>
    <p>If you did not request a password reset, please disregard this email and notify your HR
    administrator, as this may indicate an unauthorized attempt to access your account.</p>
    <p style="font-size:0.8rem;color:#8a94a3;">For security reasons, please do not share this code
    with anyone, including staff who identify themselves as company representatives.</p>
    <p>Sincerely,<br>{_company()} Payroll Team</p>"""
    return email_template(f"Password Reset Verification Code \u2014 {_company()}", body)


def payroll_generated_email_html(name: str, period_name: str, pay_date, net_pay, status: str) -> str:
    body = f"""
    <div class="status-line">Payslip Generated</div>
    <p>Dear {name},</p>
    <p>A payslip has been generated for you covering the pay period <strong>{period_name}</strong>.
    Details are summarized below:</p>
    <div class="highlight-box">
      <div class="highlight-label">Net Pay</div>
      <div class="highlight-code" style="font-size:1.4rem;">{format_currency(net_pay)}</div>
      <div class="highlight-label" style="margin-top:8px;">Pay Date: {format_date(pay_date)}</div>
    </div>
    <p>Current status: <strong>{status.title()}</strong>. Please log in to the Employee Portal at your
    convenience to review the complete breakdown of earnings and deductions.</p>
    <p>Sincerely,<br>{_company()} Payroll Team</p>"""
    return email_template(f"Payslip Generated \u2014 {_company()}", body)


_STATUS_INFO = {
    "approved": ("Payroll Approved",
                 "This is to inform you that your payslip for <strong>{period}</strong> has been "
                 "reviewed and approved by Payroll."),
    "paid": ("Payment Released",
             "This is to confirm that your salary for <strong>{period}</strong> has been released "
             "via your registered payment method."),
    "cancelled": ("Payroll Cancelled",
                  "This is to inform you that your payslip for <strong>{period}</strong> has been "
                  "cancelled. Please contact your HR/Payroll office if you have questions."),
}


def payroll_status_email_html(name: str, period_name: str, pay_date, net_pay, new_status: str, remarks: str = "") -> Optional[str]:
    info = _STATUS_INFO.get(new_status)
    if not info:
        return None
    title, msg_template = info
    msg = msg_template.format(period=period_name)
    remarks_html = f"<p style='font-size:0.85rem;color:#5b6472;'><strong>Note from HR:</strong> {remarks}</p>" if remarks else ""
    body = f"""
    <div class="status-line">{title}</div>
    <p>Dear {name},</p>
    <p>{msg}</p>
    <div class="highlight-box">
      <div class="highlight-label">Net Pay</div>
      <div class="highlight-code" style="font-size:1.4rem;">{format_currency(net_pay)}</div>
      <div class="highlight-label" style="margin-top:8px;">Pay Date: {format_date(pay_date)}</div>
    </div>
    {remarks_html}
    <p style="font-size:0.85rem;color:#5b6472;">Please log in to the Employee Portal to view the
    complete payslip breakdown.</p>
    <p>Sincerely,<br>{_company()} Payroll Team</p>"""
    return email_template(f"{title} \u2014 {_company()}", body)


# ─────────────────────────────────────────────────────────────────────────
#  SMS
# ─────────────────────────────────────────────────────────────────────────

def _normalize_ph_number(raw: str) -> Optional[str]:
    number = re.sub(r"\D", "", raw or "")
    if len(number) == 11 and number[0] == "0":
        return "63" + number[1:]
    if len(number) == 10 and number[0] == "9":
        return "63" + number
    if len(number) == 12 and number[:2] == "63":
        return number
    return None


def _sms_debug_log(number: str, payload: dict, http_status, response_text: str, error: str = "") -> None:
    try:
        log_file = LOG_DIR / "sms_debug.log"
        safe_payload = dict(payload)
        if "apikey" in safe_payload:
            safe_payload["apikey"] = safe_payload["apikey"][:4] + "\u2022\u2022\u2022\u2022(hidden)"
        from datetime import datetime
        line = (f"[{datetime.now():%Y-%m-%d %H:%M:%S}] to={number} http={http_status} "
                f"error={error or '-'} payload={safe_payload} response={response_text}\n")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:  # noqa: BLE001
        pass


def _send_via_semaphore(number: str, message: str) -> SendResult:
    cfg = get_settings().sms
    url = "https://api.semaphore.co/api/v4/messages"
    data = {"apikey": cfg.api_key, "number": number, "message": message}
    if cfg.sender_name.strip():
        data["sendername"] = cfg.sender_name.strip()
    try:
        resp = requests.post(url, data=data, timeout=15)
        _sms_debug_log(number, data, resp.status_code, resp.text)
        if resp.status_code in (200, 201):
            try:
                decoded = resp.json()
            except ValueError:
                decoded = None
            if isinstance(decoded, list) and decoded and decoded[0].get("message_id"):
                return SendResult(True)
            err = _extract_semaphore_error(decoded, resp.text)
            return SendResult(False, f"Semaphore rejected the message: {err}")
        err = _extract_semaphore_error(_safe_json(resp), resp.text)
        return SendResult(False, f"Semaphore HTTP {resp.status_code}: {err}")
    except requests.RequestException as e:
        _sms_debug_log(number, data, "N/A", "", str(e))
        return SendResult(False, f"Connection error reaching Semaphore: {e}")


def _safe_json(resp):
    try:
        return resp.json()
    except ValueError:
        return None


def _extract_semaphore_error(decoded, raw_response: str) -> str:
    if isinstance(decoded, dict):
        if "message" in decoded:
            m = decoded["message"]
            return "; ".join(m) if isinstance(m, list) else str(m)
        if "error" in decoded:
            return str(decoded["error"])
    if isinstance(decoded, list) and decoded and isinstance(decoded[0], dict) and "message" in decoded[0]:
        return str(decoded[0]["message"])
    return raw_response or "Empty response from Semaphore."


def _send_via_twilio(to_number: str, message: str) -> SendResult:
    cfg = get_settings().sms
    url = f"https://api.twilio.com/2010-04-01/Accounts/{cfg.twilio_sid}/Messages.json"
    try:
        resp = requests.post(
            url,
            auth=(cfg.twilio_sid, cfg.twilio_token),
            data={"To": to_number, "From": cfg.twilio_from, "Body": message},
            timeout=15,
        )
        decoded = _safe_json(resp) or {}
        if 200 <= resp.status_code < 300 and decoded.get("sid"):
            return SendResult(True)
        return SendResult(False, decoded.get("message") or f"Twilio HTTP {resp.status_code}: {resp.text}")
    except requests.RequestException as e:
        return SendResult(False, f"Connection error: {e}")


def send_sms(to_number: str, message: str) -> SendResult:
    cfg = get_settings().sms
    if not cfg.enabled:
        return SendResult(False, "SMS is disabled in Settings \u2192 SMS.")
    if not cfg.api_key or cfg.api_key == "YOUR_SEMAPHORE_API_KEY_HERE":
        return SendResult(False, "No SMS API key configured in Settings \u2192 SMS.")

    number = _normalize_ph_number(to_number)
    if not number:
        return SendResult(False, f'Unrecognized phone number format: "{to_number}". Expected an 11-digit PH mobile number, e.g. 09171234567.')

    if cfg.provider == "semaphore":
        return _send_via_semaphore(number, message)
    if cfg.provider == "twilio":
        return _send_via_twilio("+" + number, message)
    return SendResult(False, 'Unknown SMS provider in Settings. Use "semaphore" or "twilio".')


def sms_welcome(name: str, username: str, company: str) -> str:
    return (f"Welcome to {company}, {name}! Your PayrollPro account ({username}) is now active. "
            f"You can log in to the Employee Portal. Keep your credentials safe. - PayrollPro")


def sms_otp(otp_code: str, expiry_minutes: int) -> str:
    return f"PayrollPro: Your One-Time Password (OTP) is: {otp_code}. Valid for {expiry_minutes} minutes. Do NOT share this with anyone."


# ─────────────────────────────────────────────────────────────────────────
#  Logging + dispatch wrappers (mirrors includes/notify.php)
# ─────────────────────────────────────────────────────────────────────────

def log_notification(session: Session, channel: str, notif_type: str, recipient: str,
                      subject: Optional[str], status: str, error: Optional[str] = None,
                      employee_id: Optional[int] = None, user_id: Optional[int] = None) -> None:
    session.add(NotificationLog(
        employee_id=employee_id, user_id=user_id, channel=channel, notif_type=notif_type,
        recipient=recipient, subject=subject, status=status, error_message=error,
    ))
    session.flush()


def notify_send_email(session: Session, to_email: str, to_name: str, subject: str, html: str,
                       plain: str = "", employee_id: Optional[int] = None,
                       notif_type: str = "general", user_id: Optional[int] = None) -> SendResult:
    r = send_email(to_email, to_name, subject, html, plain)
    log_notification(session, "email", notif_type, to_email, subject,
                      "sent" if r.success else "failed", r.error, employee_id, user_id)
    return r


def notify_send_sms(session: Session, to_number: str, message: str, employee_id: Optional[int] = None,
                     notif_type: str = "general", user_id: Optional[int] = None) -> SendResult:
    if not get_settings().sms.enabled:
        return SendResult(False, None, skipped=True)
    r = send_sms(to_number, message)
    log_notification(session, "sms", notif_type, to_number, message[:100],
                      "sent" if r.success else "failed", r.error, employee_id, user_id)
    return r
