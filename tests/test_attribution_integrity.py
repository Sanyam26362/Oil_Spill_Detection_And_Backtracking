"""
Ground Truth Leakage Audit

Statically scans production attribution code to verify that
ground truth is never accessed during attribution.
"""
import pytest
import ast
import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Files that must NEVER access ground truth
PRODUCTION_FILES = [
    PROJECT_ROOT / "app" / "services" / "attribution_engine.py",
    PROJECT_ROOT / "app" / "services" / "scoring_engine.py",
    # trajectory_service.py deleted (F3) — it was never imported by production code.
    PROJECT_ROOT / "app" / "repositories" / "ais_repository.py",
    PROJECT_ROOT / "app" / "services" / "hindcast_service.py",
    PROJECT_ROOT / "app" / "services" / "drift_engine.py",
    PROJECT_ROOT / "app" / "services" / "weather_service.py",
    PROJECT_ROOT / "app" / "routers" / "attribution.py",
    PROJECT_ROOT / "app" / "routers" / "drift.py",
]

# Forbidden patterns in production code
FORBIDDEN_PATTERNS = [
    "ground_truth",
    "ground_truth_suspicious_vessel",
    "source_vessel_id",
    "true_vessel",
    "decoy_id",
    "ground_truth.json",
    "evaluation_answer",
    "_gt.json",
]


class TestLeakageAudit:
    """Verify no ground truth leakage in production attribution code."""

    def test_no_forbidden_strings_in_production_code(self):
        """Scan production files for forbidden ground truth patterns."""
        violations = []

        for filepath in PRODUCTION_FILES:
            if not filepath.exists():
                continue

            content = filepath.read_text(encoding="utf-8")
            for pattern in FORBIDDEN_PATTERNS:
                if pattern in content:
                    # Check it's not in a comment or docstring warning
                    for line_num, line in enumerate(content.splitlines(), 1):
                        stripped = line.strip()
                        if pattern in stripped:
                            # Allow in comments that say "never access"
                            if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
                                if "never" in stripped.lower() or "not" in stripped.lower() or "ground truth" in stripped.lower():
                                    continue
                            # Allow in docstrings
                            if "Ground truth is never accessed" in stripped:
                                continue
                            if "never accessed here" in stripped:
                                continue
                            violations.append(
                                f"{filepath.name}:{line_num}: '{pattern}' found in: {stripped[:100]}"
                            )

        assert not violations, (
            f"Ground truth leakage detected:\n" +
            "\n".join(violations)
        )

    def test_attribution_engine_does_not_import_ground_truth(self):
        """AttributionEngine should not import anything ground-truth related."""
        filepath = PROJECT_ROOT / "app" / "services" / "attribution_engine.py"
        if not filepath.exists():
            pytest.skip("attribution_engine.py not found")

        content = filepath.read_text(encoding="utf-8")
        
        # Parse AST to check imports
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                import_str = ast.dump(node)
                for forbidden in ["ground_truth", "evaluation", "answer"]:
                    assert forbidden not in import_str.lower(), (
                        f"Suspicious import in attribution_engine.py: {import_str}"
                    )

    def test_scoring_engine_does_not_hardcode_vessel_ids(self):
        """ScoringEngine should not contain hardcoded SYNTH vessel IDs."""
        filepath = PROJECT_ROOT / "app" / "services" / "scoring_engine.py"
        if not filepath.exists():
            pytest.skip("scoring_engine.py not found")

        content = filepath.read_text(encoding="utf-8")
        
        assert "SYNTH-000011" not in content, "Hardcoded source vessel ID in ScoringEngine"
        assert "SYNTH-S" not in content, "Hardcoded scenario vessel ID in ScoringEngine"

    def test_attribution_engine_does_not_hardcode_vessel_ids(self):
        """AttributionEngine should not contain hardcoded SYNTH vessel IDs."""
        filepath = PROJECT_ROOT / "app" / "services" / "attribution_engine.py"
        if not filepath.exists():
            pytest.skip("attribution_engine.py not found")

        content = filepath.read_text(encoding="utf-8")
        
        assert "SYNTH-000011" not in content, "Hardcoded source vessel ID in AttributionEngine"
        assert "SYNTH-S" not in content, "Hardcoded scenario vessel ID in AttributionEngine"
