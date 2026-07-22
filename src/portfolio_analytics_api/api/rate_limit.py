from dataclasses import dataclass
from ipaddress import ip_address

from fastapi import Request

from portfolio_analytics_api.application import RateLimitRule


@dataclass(frozen=True, slots=True)
class RateLimitPolicies:
    registration_ip: RateLimitRule = RateLimitRule("registration_ip", 5, 600)
    login_ip: RateLimitRule = RateLimitRule("login_ip", 10, 600)
    login_email: RateLimitRule = RateLimitRule("login_email", 5, 600)
    analytics_user: RateLimitRule = RateLimitRule("analytics_user", 20, 60)
    insights_user: RateLimitRule = RateLimitRule("insights_user", 10, 60)
    authenticated_user: RateLimitRule = RateLimitRule("authenticated_user", 120, 60)


def client_ip_identifier(request: Request, trust_proxy_headers: bool) -> str:
    direct_host = request.client.host if request.client is not None else "unknown"
    candidate = direct_host
    if trust_proxy_headers:
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            candidate = forwarded_for.split(",", maxsplit=1)[0].strip()
    try:
        return ip_address(candidate).compressed
    except ValueError:
        try:
            return ip_address(direct_host).compressed
        except ValueError:
            return "unknown"
