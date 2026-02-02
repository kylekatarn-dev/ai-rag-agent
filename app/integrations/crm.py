"""
CRM Webhook Integration.

Provides webhook-based integration with external CRM systems
(Salesforce, HubSpot, Pipedrive, etc.)
"""

import json
import hashlib
import hmac
import time
from datetime import datetime
from typing import Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum
import urllib.request
import urllib.error

from app.models.lead import Lead, LeadQuality
from app.models.property import Property
from app.utils import get_logger

logger = get_logger(__name__)


class WebhookEvent(str, Enum):
    """Webhook event types."""
    LEAD_CREATED = "lead.created"
    LEAD_QUALIFIED = "lead.qualified"
    LEAD_HOT = "lead.hot"
    LEAD_CONTACT_CAPTURED = "lead.contact_captured"
    MEETING_SCHEDULED = "meeting.scheduled"
    PROPERTY_ALERT_REGISTERED = "property_alert.registered"


@dataclass
class WebhookPayload:
    """Webhook payload structure."""
    event: str
    timestamp: str
    data: dict
    metadata: dict

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)


class CRMWebhook:
    """
    CRM Webhook client for sending lead data to external systems.

    Supports:
    - Multiple webhook endpoints
    - HMAC signature verification
    - Retry logic
    - Event filtering
    """

    def __init__(
        self,
        webhook_url: Optional[str] = None,
        secret_key: Optional[str] = None,
        enabled: bool = True,
        timeout: int = 10,
        max_retries: int = 3,
    ):
        """
        Initialize CRM webhook.

        Args:
            webhook_url: Target webhook URL
            secret_key: HMAC secret for signing requests
            enabled: Whether webhooks are enabled
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
        """
        self.webhook_url = webhook_url
        self.secret_key = secret_key
        self.enabled = enabled and webhook_url is not None
        self.timeout = timeout
        self.max_retries = max_retries

        if self.enabled:
            logger.info(f"CRM Webhook initialized: {webhook_url[:50]}...")
        else:
            logger.info("CRM Webhook disabled (no URL configured)")

    def _sign_payload(self, payload: str) -> str:
        """
        Create HMAC signature for payload.

        Args:
            payload: JSON payload string

        Returns:
            HMAC signature
        """
        if not self.secret_key:
            return ""

        signature = hmac.new(
            self.secret_key.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()

        return f"sha256={signature}"

    def _send_request(self, payload: WebhookPayload) -> tuple[bool, Optional[str]]:
        """
        Send webhook request.

        Args:
            payload: Webhook payload

        Returns:
            Tuple of (success, error_message)
        """
        if not self.enabled or not self.webhook_url:
            return True, None  # Silently succeed if disabled

        json_payload = payload.to_json()
        signature = self._sign_payload(json_payload)

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "PruchazkaRAG/1.0",
            "X-Webhook-Event": payload.event,
            "X-Webhook-Timestamp": payload.timestamp,
        }

        if signature:
            headers["X-Webhook-Signature"] = signature

        request = urllib.request.Request(
            self.webhook_url,
            data=json_payload.encode("utf-8"),
            headers=headers,
            method="POST"
        )

        for attempt in range(self.max_retries):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    if 200 <= response.status < 300:
                        logger.info(f"Webhook sent successfully: {payload.event}")
                        return True, None

                    error = f"Unexpected status: {response.status}"
                    logger.warning(f"Webhook failed (attempt {attempt + 1}): {error}")

            except urllib.error.HTTPError as e:
                error = f"HTTP {e.code}: {e.reason}"
                logger.warning(f"Webhook failed (attempt {attempt + 1}): {error}")

            except urllib.error.URLError as e:
                error = f"Connection error: {e.reason}"
                logger.warning(f"Webhook failed (attempt {attempt + 1}): {error}")

            except Exception as e:
                error = str(e)
                logger.error(f"Webhook error (attempt {attempt + 1}): {error}")

            # Wait before retry (exponential backoff)
            if attempt < self.max_retries - 1:
                time.sleep(2 ** attempt)

        return False, error

    def send_lead_created(self, lead: Lead) -> bool:
        """
        Send lead created event.

        Args:
            lead: The created lead

        Returns:
            True if successful
        """
        payload = self._build_lead_payload(WebhookEvent.LEAD_CREATED, lead)
        success, _ = self._send_request(payload)
        return success

    def send_lead_qualified(
        self,
        lead: Lead,
        matched_properties: Optional[list[Property]] = None
    ) -> bool:
        """
        Send lead qualified event (when score is calculated).

        Args:
            lead: The qualified lead
            matched_properties: Properties matched to the lead

        Returns:
            True if successful
        """
        data = self._lead_to_dict(lead)

        if matched_properties:
            data["matched_properties"] = [
                {
                    "id": p.id,
                    "type": p.property_type,
                    "location": p.location,
                    "area_sqm": p.area_sqm,
                    "price_czk_sqm": p.price_czk_sqm,
                }
                for p in matched_properties[:5]
            ]

        payload = WebhookPayload(
            event=WebhookEvent.LEAD_QUALIFIED.value,
            timestamp=datetime.utcnow().isoformat(),
            data=data,
            metadata={"source": "rag_assistant"},
        )

        success, _ = self._send_request(payload)
        return success

    def send_lead_hot(self, lead: Lead) -> bool:
        """
        Send lead hot event (when lead becomes HOT quality).

        Args:
            lead: The hot lead

        Returns:
            True if successful
        """
        if lead.lead_quality != LeadQuality.HOT:
            return True  # Skip if not hot

        payload = self._build_lead_payload(WebhookEvent.LEAD_HOT, lead)
        payload.metadata["priority"] = "high"
        payload.metadata["action_required"] = "immediate_contact"

        success, _ = self._send_request(payload)
        return success

    def send_contact_captured(self, lead: Lead) -> bool:
        """
        Send contact captured event.

        Args:
            lead: Lead with captured contact info

        Returns:
            True if successful
        """
        if not lead.has_contact_info:
            return True  # Skip if no contact

        payload = self._build_lead_payload(WebhookEvent.LEAD_CONTACT_CAPTURED, lead)

        success, _ = self._send_request(payload)
        return success

    def send_meeting_scheduled(
        self,
        lead: Lead,
        meeting_type: str,
        scheduled_time: Optional[datetime] = None
    ) -> bool:
        """
        Send meeting scheduled event.

        Args:
            lead: The lead
            meeting_type: Type of meeting (call, video, in_person)
            scheduled_time: Scheduled meeting time

        Returns:
            True if successful
        """
        data = self._lead_to_dict(lead)
        data["meeting"] = {
            "type": meeting_type,
            "scheduled_time": scheduled_time.isoformat() if scheduled_time else None,
        }

        payload = WebhookPayload(
            event=WebhookEvent.MEETING_SCHEDULED.value,
            timestamp=datetime.utcnow().isoformat(),
            data=data,
            metadata={"source": "rag_assistant"},
        )

        success, _ = self._send_request(payload)
        return success

    def send_property_alert_registered(
        self,
        lead: Lead,
        criteria: dict
    ) -> bool:
        """
        Send property alert registered event.

        Args:
            lead: The lead
            criteria: Search criteria for alerts

        Returns:
            True if successful
        """
        data = self._lead_to_dict(lead)
        data["alert_criteria"] = criteria

        payload = WebhookPayload(
            event=WebhookEvent.PROPERTY_ALERT_REGISTERED.value,
            timestamp=datetime.utcnow().isoformat(),
            data=data,
            metadata={"source": "rag_assistant"},
        )

        success, _ = self._send_request(payload)
        return success

    def _build_lead_payload(self, event: WebhookEvent, lead: Lead) -> WebhookPayload:
        """Build standard lead payload."""
        return WebhookPayload(
            event=event.value,
            timestamp=datetime.utcnow().isoformat(),
            data=self._lead_to_dict(lead),
            metadata={"source": "rag_assistant"},
        )

    def _lead_to_dict(self, lead: Lead) -> dict:
        """Convert lead to webhook-friendly dict."""
        return {
            "id": lead.id,
            "created_at": lead.created_at.isoformat(),
            "contact": {
                "name": lead.name,
                "email": lead.email,
                "phone": lead.phone,
                "company": lead.company,
                "preferred_method": lead.preferred_contact_method,
                "preferred_time": lead.preferred_call_time,
            },
            "requirements": {
                "property_type": lead.property_type,
                "min_area_sqm": lead.min_area_sqm,
                "max_area_sqm": lead.max_area_sqm,
                "preferred_locations": lead.preferred_locations,
                "max_price_czk_sqm": lead.max_price_czk_sqm,
                "move_in_urgency": lead.move_in_urgency,
            },
            "qualification": {
                "score": lead.lead_score,
                "quality": lead.lead_quality.value if lead.lead_quality else None,
                "customer_type": lead.customer_type.value if lead.customer_type else None,
            },
            "preferences": {
                "wants_notifications": lead.wants_notifications,
                "wants_broker_contact": lead.wants_broker_contact,
            },
            "conversation_summary": lead.conversation_summary,
        }


# Singleton instance
_crm_webhook: CRMWebhook | None = None


def get_crm_webhook() -> CRMWebhook:
    """Get singleton CRM webhook instance."""
    global _crm_webhook
    if _crm_webhook is None:
        import os
        _crm_webhook = CRMWebhook(
            webhook_url=os.getenv("CRM_WEBHOOK_URL"),
            secret_key=os.getenv("CRM_WEBHOOK_SECRET"),
            enabled=os.getenv("CRM_WEBHOOK_ENABLED", "false").lower() == "true",
        )
    return _crm_webhook
