"""Enterprise Connectors Package for OrgBridge AI."""

from src.connectors.base import BaseConnector
from src.connectors.github import GitHubConnector, github_connector
from src.connectors.jira import JiraConnector, jira_connector
from src.connectors.slack import SlackConnector, slack_connector
from src.connectors.security_pipeline import (
    verify_slack_webhook,
    verify_github_webhook,
    verify_jira_webhook,
    scrub_untrusted_text,
    redact_sensitive_data,
    TokenVault,
    OAuthMutex,
    token_vault,
    generate_person_id,
    calculate_identity_confidence,
    is_bot_event,
)

__all__ = [
    "BaseConnector",
    "GitHubConnector",
    "github_connector",
    "JiraConnector",
    "jira_connector",
    "SlackConnector",
    "slack_connector",
    "verify_slack_webhook",
    "verify_github_webhook",
    "verify_jira_webhook",
    "scrub_untrusted_text",
    "redact_sensitive_data",
    "TokenVault",
    "OAuthMutex",
    "token_vault",
    "generate_person_id",
    "calculate_identity_confidence",
    "is_bot_event",
]
