# Integrations module
from .crm import CRMWebhook, get_crm_webhook
from .email import EmailService, get_email_service

__all__ = [
    "CRMWebhook",
    "get_crm_webhook",
    "EmailService",
    "get_email_service",
]
