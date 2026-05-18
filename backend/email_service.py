"""Resend ile email gönderim servisi."""
import os
import asyncio
import logging
import resend
from typing import Optional

logger = logging.getLogger(__name__)

resend.api_key = os.environ.get("RESEND_API_KEY", "")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "onboarding@resend.dev")
SENDER_NAME = os.environ.get("SENDER_NAME", "EY Finans")


def _wrap_html(title: str, body_html: str) -> str:
    """Apple/Notion stili minimal HTML email şablonu."""
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{title}</title>
</head>
<body style="margin:0;padding:0;background:#FBFBFD;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;color:#1D1D1F;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#FBFBFD;padding:40px 16px;">
  <tr><td align="center">
    <table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" style="background:#FFFFFF;border-radius:16px;border:1px solid #E5E5EA;overflow:hidden;max-width:600px;width:100%;">
      <tr><td style="padding:32px 40px 16px 40px;">
        <div style="font-size:14px;font-weight:600;letter-spacing:0.5px;color:#86868B;text-transform:uppercase;">EY Finans</div>
        <h1 style="margin:8px 0 0 0;font-size:24px;font-weight:600;color:#1D1D1F;letter-spacing:-0.5px;">{title}</h1>
      </td></tr>
      <tr><td style="padding:8px 40px 32px 40px;font-size:15px;line-height:1.6;color:#1D1D1F;">
        {body_html}
      </td></tr>
      <tr><td style="padding:20px 40px;background:#F5F5F7;border-top:1px solid #E5E5EA;font-size:12px;color:#86868B;">
        Bu otomatik bir bildirimdir. Yanıtlamayınız.<br/>
        © EY Finans Platform
      </td></tr>
    </table>
  </td></tr>
</table>
</body>
</html>
"""


async def send_email(to_email: str, subject: str, body_html: str, title: Optional[str] = None) -> bool:
    """Email gönder. asyncio.to_thread ile non-blocking."""
    if not resend.api_key:
        logger.warning("RESEND_API_KEY tanımlı değil, email gönderilmedi: %s", to_email)
        return False
    html = _wrap_html(title or subject, body_html)
    params = {
        "from": f"{SENDER_NAME} <{SENDER_EMAIL}>",
        "to": [to_email],
        "subject": subject,
        "html": html,
    }
    try:
        result = await asyncio.to_thread(resend.Emails.send, params)
        logger.info("Email gönderildi: %s id=%s", to_email, result.get("id"))
        return True
    except Exception as e:
        logger.error("Email gönderme hatası %s: %s", to_email, e)
        return False


async def send_password_reset(to_email: str, reset_link: str) -> bool:
    body = f"""
    <p>Merhaba,</p>
    <p>Şifrenizi sıfırlamak için aşağıdaki bağlantıya 1 saat içinde tıklayın:</p>
    <p style="margin:24px 0;">
      <a href="{reset_link}" style="background:#111111;color:#FFFFFF;padding:12px 24px;border-radius:10px;text-decoration:none;font-weight:500;display:inline-block;">Şifreyi Sıfırla</a>
    </p>
    <p style="color:#86868B;font-size:13px;">Bu isteği siz yapmadıysanız bu emaili göz ardı edebilirsiniz.</p>
    """
    return await send_email(to_email, "Şifre Sıfırlama", body, "Şifre Sıfırlama")


async def send_payment_reminder(to_email: str, payable: dict, days_until: int) -> bool:
    when = f"{days_until} gün sonra" if days_until > 0 else ("bugün" if days_until == 0 else f"{abs(days_until)} gün geçti")
    amount = f"{payable.get('usd_amount', 0):,.2f} USD"
    rows = "".join([
        f"<tr><td style='padding:6px 0;color:#86868B;'>Firma</td><td style='padding:6px 0;text-align:right;'>{payable.get('vendor','-')}</td></tr>",
        f"<tr><td style='padding:6px 0;color:#86868B;'>Açıklama</td><td style='padding:6px 0;text-align:right;'>{payable.get('description','-')}</td></tr>",
        f"<tr><td style='padding:6px 0;color:#86868B;'>Vade</td><td style='padding:6px 0;text-align:right;font-weight:500;'>{payable.get('due_date','-')}</td></tr>",
        f"<tr><td style='padding:6px 0;color:#86868B;'>Tutar</td><td style='padding:6px 0;text-align:right;font-weight:600;'>{amount}</td></tr>",
    ])
    body = f"""
    <p>Aşağıdaki borç ödemesinin vadesi <strong>{when}</strong>:</p>
    <table cellpadding="0" cellspacing="0" border="0" width="100%" style="margin:20px 0;border:1px solid #E5E5EA;border-radius:12px;padding:16px 20px;">
    {rows}
    </table>
    <p style="color:#86868B;font-size:13px;">EY Finans Platform'dan otomatik gönderildi.</p>
    """
    return await send_email(to_email, f"Vade Hatırlatma: {payable.get('vendor', 'Borç')}", body, "Vade Hatırlatma")
