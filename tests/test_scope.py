"""Tests for engagement scope: type detection, profiles, and boundaries.

Pure logic — no LLM or external services (stdlib only)."""

import pytest

from src.scope import (
    Scope, EngagementType, detect_type, profile_for,
)
from src.tracker.task_tree import Phase


# ── Type detection ────────────────────────────────────────────────────────────

def test_detect_web():
    assert detect_type("http://localhost:9999") == EngagementType.WEB
    assert detect_type("https://shop.example") == EngagementType.WEB


def test_detect_api():
    assert detect_type("http://host/api/v1/users") == EngagementType.API
    assert detect_type("https://host/swagger.json") == EngagementType.API


def test_detect_network():
    assert detect_type("10.0.0.5") == EngagementType.NETWORK
    assert detect_type("10.0.0.0/24") == EngagementType.NETWORK
    assert detect_type("target.internal") == EngagementType.NETWORK


# ── Scope construction ────────────────────────────────────────────────────────

def test_for_target_autodetects():
    s = Scope.for_target("http://localhost:9999")
    assert s.engagement_type == EngagementType.WEB
    assert s.targets == ["http://localhost:9999"]


def test_for_target_override():
    s = Scope.for_target("http://localhost:9999", engagement_type=EngagementType.API)
    assert s.engagement_type == EngagementType.API


# ── Boundary enforcement ──────────────────────────────────────────────────────

def test_in_scope_command_allowed():
    s = Scope.for_target("http://localhost:9999")
    ok, host = s.is_command_in_scope("whatweb http://localhost:9999")
    assert ok and host is None


def test_loopback_allowed():
    s = Scope.for_target("http://localhost:9999")
    ok, _ = s.is_command_in_scope("curl http://127.0.0.1:9999/robots.txt")
    assert ok


def test_out_of_scope_url_blocked():
    s = Scope.for_target("http://localhost:9999")
    ok, host = s.is_command_in_scope("curl http://evil.com/x")
    assert not ok and host == "evil.com"


def test_out_of_scope_ip_sweep_blocked():
    s = Scope.for_target("10.0.0.5", engagement_type=EngagementType.NETWORK)
    ok, host = s.is_command_in_scope("nmap -sV 10.0.0.0/8")
    assert not ok               # 10.0.0.0 is not the in-scope 10.0.0.5


def test_command_without_host_allowed():
    s = Scope.for_target("http://localhost:9999")
    ok, _ = s.is_command_in_scope("id && uname -a")
    assert ok


def test_added_target_becomes_in_scope():
    s = Scope.for_target("http://localhost:9999")
    s.targets.append("10.0.0.9")
    ok, _ = s.is_command_in_scope("nmap -sV 10.0.0.9")
    assert ok


# ── Methodology profiles ──────────────────────────────────────────────────────

def test_web_profile_is_web_shaped():
    web = profile_for(EngagementType.WEB)
    assert web and web[0][0] == Phase.RECON
    assert "fingerprint" in web[0][1].lower()
    # No network host-discovery / port-sweep task in a web engagement.
    joined = " ".join(d.lower() for _, d in web)
    assert "host discovery" not in joined and "nmap -sn" not in joined


def test_network_profile_starts_with_discovery():
    net = profile_for(EngagementType.NETWORK)
    assert net and "host discovery" in net[0][1].lower()


def test_api_and_host_profiles_present():
    assert profile_for(EngagementType.API)
    assert profile_for(EngagementType.HOST)
    assert profile_for(EngagementType.GENERIC) == []   # generic falls back to LLM/default


def test_scope_prompt_mentions_type_and_rules():
    s = Scope.for_target("http://localhost:9999")
    p = s.scope_prompt()
    assert "WEB" in p and "ENGAGEMENT SCOPE" in p
    assert "do not run" in p.lower() or "do NOT run".lower() in p.lower()
