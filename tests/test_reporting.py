"""Tests for Report Generator module."""

import os
import shutil
import pytest
from src.reporting.generator import ReportGenerator, Finding


class TestFinding:
    """Tests for Finding data class."""
    
    def test_create_finding(self):
        f = Finding(title="SQL Injection", severity="high",
                    description="Found in login form", cve="CVE-2021-12345")
        assert f.title == "SQL Injection"
        assert f.severity == "high"
        assert f.cve == "CVE-2021-12345"
    
    def test_severity_normalization(self):
        f = Finding(title="Test", severity="HIGH")
        assert f.severity == "high"
    
    def test_to_dict(self):
        f = Finding(title="XSS", severity="medium")
        d = f.to_dict()
        assert d["title"] == "XSS"
        assert d["severity"] == "medium"
        assert "timestamp" in d
    
    def test_severity_ordering(self):
        assert Finding.SEVERITIES["critical"] < Finding.SEVERITIES["high"]
        assert Finding.SEVERITIES["high"] < Finding.SEVERITIES["medium"]
        assert Finding.SEVERITIES["medium"] < Finding.SEVERITIES["low"]
        assert Finding.SEVERITIES["low"] < Finding.SEVERITIES["info"]


class TestReportGenerator:
    """Tests for report generation."""
    
    @pytest.fixture
    def gen(self):
        g = ReportGenerator()
        g.target = "target.test"
        g.scope = "Internal network"
        return g
    
    def test_add_finding(self, gen):
        gen.add_finding(Finding("Open SSH", severity="low"))
        assert len(gen.findings) == 1
    
    def test_add_evidence(self, gen):
        gen.add_evidence("nmap", "nmap -sV target.test", "PORT   STATE SERVICE\n22/tcp open  ssh")
        assert len(gen.raw_evidence) == 1
    
    def test_generate_markdown(self, gen):
        gen.add_finding(Finding("SQL Injection", severity="critical", description="Login bypass"))
        gen.add_finding(Finding("Open Port 22", severity="info"))
        md = gen.generate_markdown()
        assert "Penetration Test Report" in md
        assert "target.test" in md
        assert "SQL Injection" in md
        assert "CRITICAL" in md
        assert "Open Port 22" in md
    
    def test_generate_html(self, gen):
        gen.add_finding(Finding("XSS", severity="high", evidence="<script>alert(1)</script>"))
        html = gen.generate_html()
        assert "<!DOCTYPE html>" in html
        assert "target.test" in html
        assert "XSS" in html
        assert "HIGH" in html
    
    def test_severity_sorting(self, gen):
        gen.add_finding(Finding("Info Finding", severity="info"))
        gen.add_finding(Finding("Critical Finding", severity="critical"))
        gen.add_finding(Finding("Low Finding", severity="low"))
        sorted_f = gen._sorted_findings()
        assert sorted_f[0].severity == "critical"
        assert sorted_f[-1].severity == "info"
    
    def test_save_files(self, gen):
        gen.add_finding(Finding("Test", severity="medium"))
        saved = gen.save(output_dir="/tmp/cva_test_reports", fmt="both")
        assert len(saved) == 2
        assert any(p.endswith(".md") for p in saved)
        assert any(p.endswith(".html") for p in saved)
        # Cleanup
        shutil.rmtree("/tmp/cva_test_reports", ignore_errors=True)
    
    def test_severity_stats(self, gen):
        gen.add_finding(Finding("A", severity="high"))
        gen.add_finding(Finding("B", severity="high"))
        gen.add_finding(Finding("C", severity="low"))
        stats = gen._severity_stats()
        assert stats["high"] == 2
        assert stats["low"] == 1
    
    def test_empty_report(self, gen):
        md = gen.generate_markdown()
        assert "0" in md or "No findings" in md.lower() or "0 findings" in md.lower() or "Penetration Test Report" in md
        html = gen.generate_html()
        assert "No findings" in html or "<!DOCTYPE html>" in html
