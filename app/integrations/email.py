"""
Email Notification Service.

Provides email sending capabilities for property alerts,
broker notifications, and lead follow-ups.
"""

import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dataclasses import dataclass
from typing import Optional
from datetime import datetime

from app.models.lead import Lead
from app.models.property import Property
from app.utils import get_logger

logger = get_logger(__name__)


@dataclass
class EmailConfig:
    """Email service configuration."""
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    username: Optional[str] = None
    password: Optional[str] = None
    from_email: str = "noreply@example.com"
    from_name: str = "Realitni AI Asistent"
    use_tls: bool = True
    enabled: bool = False


class EmailService:
    """
    Email service for sending notifications.

    Supports:
    - SMTP with TLS
    - HTML and plain text emails
    - Templates for common email types
    - Configurable sender
    """

    def __init__(self, config: Optional[EmailConfig] = None):
        """
        Initialize email service.

        Args:
            config: Email configuration
        """
        self.config = config or EmailConfig()
        self.enabled = (
            self.config.enabled and
            self.config.username is not None and
            self.config.password is not None
        )

        if self.enabled:
            logger.info(f"Email service initialized: {self.config.smtp_host}")
        else:
            logger.info("Email service disabled (credentials not configured)")

    def _create_connection(self) -> smtplib.SMTP:
        """Create SMTP connection."""
        server = smtplib.SMTP(self.config.smtp_host, self.config.smtp_port)

        if self.config.use_tls:
            context = ssl.create_default_context()
            server.starttls(context=context)

        if self.config.username and self.config.password:
            server.login(self.config.username, self.config.password)

        return server

    def send_email(
        self,
        to_email: str,
        subject: str,
        body_html: str,
        body_text: Optional[str] = None,
    ) -> tuple[bool, Optional[str]]:
        """
        Send an email.

        Args:
            to_email: Recipient email address
            subject: Email subject
            body_html: HTML body content
            body_text: Plain text body (optional)

        Returns:
            Tuple of (success, error_message)
        """
        if not self.enabled:
            logger.debug(f"Email skipped (disabled): {subject} -> {to_email}")
            return True, None

        try:
            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = f"{self.config.from_name} <{self.config.from_email}>"
            message["To"] = to_email

            # Add plain text version
            if body_text:
                message.attach(MIMEText(body_text, "plain", "utf-8"))

            # Add HTML version
            message.attach(MIMEText(body_html, "html", "utf-8"))

            # Send
            with self._create_connection() as server:
                server.sendmail(
                    self.config.from_email,
                    to_email,
                    message.as_string()
                )

            logger.info(f"Email sent: {subject} -> {to_email}")
            return True, None

        except smtplib.SMTPAuthenticationError as e:
            error = f"Authentication failed: {e}"
            logger.error(error)
            return False, error

        except smtplib.SMTPException as e:
            error = f"SMTP error: {e}"
            logger.error(error)
            return False, error

        except Exception as e:
            error = f"Email error: {e}"
            logger.error(error)
            return False, error

    def send_property_alert(
        self,
        to_email: str,
        to_name: Optional[str],
        properties: list[Property],
        criteria: dict,
    ) -> bool:
        """
        Send property alert email.

        Args:
            to_email: Recipient email
            to_name: Recipient name
            properties: New matching properties
            criteria: Search criteria

        Returns:
            True if successful
        """
        name = to_name or "Vážený klient"

        # Build property list HTML
        property_html = ""
        for prop in properties[:5]:
            property_html += f"""
            <div style="border: 1px solid #ddd; padding: 15px; margin: 10px 0; border-radius: 8px;">
                <h3 style="margin: 0 0 10px 0; color: #333;">
                    {prop.property_type_cz.upper()} - {prop.location}
                    {"&#128293;" if prop.is_hot else ""}
                </h3>
                <ul style="margin: 0; padding-left: 20px;">
                    <li>Plocha: {prop.area_sqm} m²</li>
                    <li>Cena: {prop.price_czk_sqm} Kč/m²/měsíc ({prop.total_monthly_rent:,} Kč celkem)</li>
                    <li>Dostupnost: {"ihned" if prop.is_available_now else prop.availability}</li>
                </ul>
            </div>
            """

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
        </head>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <h1 style="color: #2c3e50;">Nové nemovitosti pro vás</h1>

            <p>Dobrý den, {name}!</p>

            <p>Máme pro vás <strong>{len(properties)}</strong> nových nemovitostí odpovídajících vašim kritériím:</p>

            {property_html}

            <p style="margin-top: 20px;">
                <a href="#" style="background-color: #3498db; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">
                    Zobrazit všechny nabídky
                </a>
            </p>

            <hr style="margin: 30px 0; border: none; border-top: 1px solid #eee;">

            <p style="color: #666; font-size: 12px;">
                Tento email byl zaslán na základě vaší registrace k odběru novinek.<br>
                Pro odhlášení klikněte <a href="#">zde</a>.
            </p>
        </body>
        </html>
        """

        text = f"""
        Dobrý den, {name}!

        Máme pro vás {len(properties)} nových nemovitostí.

        {"".join([f"- {p.property_type_cz.upper()} v {p.location}, {p.area_sqm}m², {p.price_czk_sqm} Kč/m²\n" for p in properties[:5]])}

        Pro více informací navštivte naši webovou stránku.
        """

        success, _ = self.send_email(
            to_email=to_email,
            subject=f"[Nová nabídka] {len(properties)} nemovitostí pro vás",
            body_html=html,
            body_text=text,
        )
        return success

    def send_broker_notification(
        self,
        broker_email: str,
        broker_name: str,
        lead: Lead,
        summary: str,
    ) -> bool:
        """
        Send new lead notification to broker.

        Args:
            broker_email: Broker's email
            broker_name: Broker's name
            lead: The new lead
            summary: Conversation summary

        Returns:
            True if successful
        """
        quality_emoji = {
            "hot": "&#128293; HOT",
            "warm": "&#127777; WARM",
            "cold": "&#10052; COLD",
        }.get(lead.lead_quality.value if lead.lead_quality else "cold", "")

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
        </head>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <h1 style="color: #2c3e50;">Nový lead k zpracování</h1>

            <div style="background: #f8f9fa; padding: 15px; border-radius: 8px; margin: 20px 0;">
                <h2 style="margin: 0 0 10px 0;">
                    Lead Score: {lead.lead_score}/100 {quality_emoji}
                </h2>
            </div>

            <h3>Kontaktní údaje</h3>
            <ul>
                <li><strong>Jméno:</strong> {lead.name or "Neuvedeno"}</li>
                <li><strong>Email:</strong> {lead.email or "Neuvedeno"}</li>
                <li><strong>Telefon:</strong> {lead.phone or "Neuvedeno"}</li>
                <li><strong>Firma:</strong> {lead.company or "Neuvedeno"}</li>
            </ul>

            <h3>Požadavky</h3>
            <ul>
                <li><strong>Typ:</strong> {lead.property_type or "Neurčeno"}</li>
                <li><strong>Plocha:</strong> {lead.min_area_sqm or "?"} - {lead.max_area_sqm or "?"} m²</li>
                <li><strong>Lokalita:</strong> {", ".join(lead.preferred_locations) if lead.preferred_locations else "Neurčeno"}</li>
                <li><strong>Rozpočet:</strong> max {lead.max_price_czk_sqm or "?"} Kč/m²</li>
                <li><strong>Nástup:</strong> {lead.move_in_urgency or "Neurčeno"}</li>
            </ul>

            <h3>Shrnutí konverzace</h3>
            <p style="background: #fff; border-left: 3px solid #3498db; padding: 10px 15px;">
                {summary or "Shrnutí není k dispozici."}
            </p>

            <p style="margin-top: 20px;">
                <a href="#" style="background-color: #27ae60; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">
                    Zobrazit detail leadu
                </a>
            </p>

            <hr style="margin: 30px 0; border: none; border-top: 1px solid #eee;">

            <p style="color: #666; font-size: 12px;">
                Tento email byl automaticky vygenerován AI asistentem.
            </p>
        </body>
        </html>
        """

        quality_text = lead.lead_quality.value.upper() if lead.lead_quality else "COLD"
        success, _ = self.send_email(
            to_email=broker_email,
            subject=f"[{quality_text}] Nový lead - {lead.name or 'Neznámý klient'}",
            body_html=html,
        )
        return success

    def send_meeting_confirmation(
        self,
        to_email: str,
        to_name: Optional[str],
        meeting_type: str,
        meeting_time: Optional[datetime],
        broker_name: str,
    ) -> bool:
        """
        Send meeting confirmation to client.

        Args:
            to_email: Client email
            to_name: Client name
            meeting_type: Type of meeting
            meeting_time: Scheduled time
            broker_name: Broker's name

        Returns:
            True if successful
        """
        name = to_name or "Vážený klient"
        meeting_types = {
            "call": "Telefonát",
            "video": "Videohovor",
            "meeting": "Osobní schůzka",
        }
        type_name = meeting_types.get(meeting_type, "Schůzka")

        time_str = (
            meeting_time.strftime("%d.%m.%Y v %H:%M")
            if meeting_time else "bude upřesněno"
        )

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
        </head>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <h1 style="color: #2c3e50;">Potvrzení schůzky</h1>

            <p>Dobrý den, {name}!</p>

            <p>Vaše schůzka byla úspěšně naplánována.</p>

            <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">
                <p style="margin: 5px 0;"><strong>Typ:</strong> {type_name}</p>
                <p style="margin: 5px 0;"><strong>Termín:</strong> {time_str}</p>
                <p style="margin: 5px 0;"><strong>Makléř:</strong> {broker_name}</p>
            </div>

            {"<p>Odkaz na videohovor vám zašleme před schůzí na tento email.</p>" if meeting_type == "video" else ""}

            <p>Těšíme se na setkání s vámi!</p>

            <hr style="margin: 30px 0; border: none; border-top: 1px solid #eee;">

            <p style="color: #666; font-size: 12px;">
                V případě potřeby změny termínu nás prosím kontaktujte.
            </p>
        </body>
        </html>
        """

        success, _ = self.send_email(
            to_email=to_email,
            subject=f"Potvrzení schůzky - {type_name} {time_str}",
            body_html=html,
        )
        return success


# Singleton instance
_email_service: EmailService | None = None


def get_email_service() -> EmailService:
    """Get singleton email service instance."""
    global _email_service
    if _email_service is None:
        import os
        config = EmailConfig(
            smtp_host=os.getenv("SMTP_HOST", "smtp.gmail.com"),
            smtp_port=int(os.getenv("SMTP_PORT", "587")),
            username=os.getenv("SMTP_USERNAME"),
            password=os.getenv("SMTP_PASSWORD"),
            from_email=os.getenv("EMAIL_FROM", "noreply@example.com"),
            from_name=os.getenv("EMAIL_FROM_NAME", "Realitní AI Asistent"),
            enabled=os.getenv("EMAIL_ENABLED", "false").lower() == "true",
        )
        _email_service = EmailService(config)
    return _email_service
