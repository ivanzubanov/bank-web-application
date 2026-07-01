import aiosmtplib
from email.message import EmailMessage
from bank_notify.config import settings


async def send_email(to_email: str, subject: str, html_content: str) -> None:
    message = EmailMessage()
    message["From"] = settings.SMTP_USER or "noreply@bank.com"
    message["To"] = to_email
    message["Subject"] = subject

    message.add_alternative(html_content, subtype="html")

    async with aiosmtplib.SMTP(
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            use_tls=False
    ) as server:
        if settings.SMTP_USER and settings.SMTP_PASSWORD:
            await server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)

        await server.send_message(message)


def render_verification_template(username: str, code: str) -> str:
    """Simple HTML template for email verification."""
    return f"""
    <html>
        <body>
            <h2>Hello, {username}!</h2>
            <p>Your activation code for Bank Web Application is:</p>
            <h3 style="color: #4F46E5;">{code}</h3>
            <p>If you did not request this code, please ignore this email.</p>
        </body>
    </html>
    """


def render_mass_mail_template(username: str, text: str) -> str:
    """HTML template for important administrative broadcasts."""
    return f"""
    <html>
        <body style="font-family: sans-serif; background-color: #f4f4f5; padding: 20px;">
            <div style="background-color: #ffffff; padding: 20px; border-radius: 8px; max-width: 600px; margin: 0 auto;">
                <h2 style="color: #dc2626;">⚠️ Important Administrative Notice</h2>
                <p>Dear <strong>{username}</strong>,</p>
                <p>{text}</p>
                <hr style="border: none; border-top: 1px solid #e4e4e7; margin: 20px 0;"/>
                <small style="color: #71717a;">Best regards,<br/>Bank Security Team</small>
            </div>
        </body>
    </html>
    """