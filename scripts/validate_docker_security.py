#!/usr/bin/env python3
"""
Docker Security Validation Script
Checks for security issues and leaked secrets in Docker configuration.
"""

import os
import re
import sys
from pathlib import Path


class SecurityValidator:
    """Validates Docker configuration for security issues."""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.issues = []
        self.warnings = []

    def check_dockerfile_security(self) -> None:
        """Check Dockerfile for security best practices."""
        dockerfile_path = self.project_root / "Dockerfile"

        if not dockerfile_path.exists():
            self.issues.append("❌ Dockerfile not found")
            return

        content = dockerfile_path.read_text()

        # Check for non-root user
        if "USER appuser" not in content:
            self.issues.append("❌ Dockerfile doesn't switch to non-root user")
        else:
            print("✅ Dockerfile uses non-root user")

        # Check for HEALTHCHECK
        if "HEALTHCHECK" not in content:
            self.warnings.append("⚠️  No HEALTHCHECK defined in Dockerfile")
        else:
            print("✅ Dockerfile includes health check")

        # Check for multi-stage build
        if "FROM" not in content or content.count("FROM") < 2:
            self.warnings.append("⚠️  Not using multi-stage build")
        else:
            print("✅ Multi-stage build detected")

    def check_dockerignore(self) -> None:
        """Check .dockerignore file for security."""
        dockerignore_path = self.project_root / ".dockerignore"

        if not dockerignore_path.exists():
            self.issues.append("❌ .dockerignore file missing")
            return

        content = dockerignore_path.read_text()

        # Check for sensitive files
        sensitive_patterns = [".env", ".cursor/", "tests/", "*.log"]

        for pattern in sensitive_patterns:
            if pattern not in content:
                self.warnings.append(f"⚠️  .dockerignore missing pattern: {pattern}")
            else:
                print(f"✅ .dockerignore excludes: {pattern}")

    def check_for_hardcoded_secrets(self) -> None:
        """Scan for hardcoded secrets in source files."""
        print("🔍 Scanning for hardcoded secrets...")

        # Patterns that might indicate hardcoded secrets
        secret_patterns = [
            r'api[_-]?key\s*=\s*["\'][^"\']{20,}["\']',
            r'secret\s*=\s*["\'][^"\']{20,}["\']',
            r'token\s*=\s*["\'][^"\']{20,}["\']',
            r'password\s*=\s*["\'][^"\']{8,}["\']',
            # Only flag actual production URLs, not placeholders or examples
            r'(?<!default=")[^"]*https://(?!placeholder|example|your-)[a-zA-Z0-9-]+\.supabase\.co(?!/storage)',
            r'(?<!default=")[^"]*https://(?!placeholder|example|your-)[a-zA-Z0-9-]+\.upstash\.io',
        ]

        # Exclude these directories/files from scanning
        exclude_patterns = [
            "/.git/",
            "/node_modules/",
            "/__pycache__/",
            "/.venv/",
            "/logs/",
            "/.env.example",
            "/scripts/validate_docker_security.py",  # This file
            "/README.md",  # Documentation file with template URLs
            "/scripts/prd.txt",  # PRD with example URLs
            "/app/services/README.md",  # Service documentation
        ]

        for root, _dirs, files in os.walk(self.project_root):
            # Skip excluded directories
            root_str = str(root)
            if any(exclude in root_str for exclude in exclude_patterns):
                continue

            for file in files:
                if file.endswith((".py", ".yml", ".yaml", ".json", ".md", ".txt")):
                    file_path = Path(root) / file

                    # Skip excluded files
                    relative_path = str(file_path.relative_to(self.project_root))
                    if any(
                        exclude.lstrip("/") in relative_path
                        for exclude in exclude_patterns
                    ):
                        continue

                    try:
                        content = file_path.read_text(encoding="utf-8")

                        for pattern in secret_patterns:
                            matches = re.finditer(pattern, content, re.IGNORECASE)
                            for match in matches:
                                line_num = content[: match.start()].count("\n") + 1
                                self.issues.append(
                                    f"❌ Potential secret in {file_path.relative_to(self.project_root)}:{line_num} - {match.group()[:50]}..."
                                )

                    except UnicodeDecodeError:
                        # Skip binary files
                        continue

    def check_env_example(self) -> None:
        """Check that .env.example exists and .env is gitignored."""
        env_example = self.project_root / ".env.example"
        gitignore = self.project_root / ".gitignore"

        if not env_example.exists():
            self.warnings.append("⚠️  .env.example template missing")
        else:
            print("✅ .env.example template exists")

        if not gitignore.exists():
            self.issues.append("❌ .gitignore missing")
            return

        gitignore_content = gitignore.read_text()
        if ".env" not in gitignore_content:
            self.issues.append("❌ .env not in .gitignore")
        else:
            print("✅ .env files are gitignored")

    def run_validation(self) -> bool:
        """Run all security validations."""
        print("🔒 Running Docker Security Validation...")
        print("=" * 50)

        self.check_dockerfile_security()
        self.check_dockerignore()
        self.check_env_example()
        self.check_for_hardcoded_secrets()

        print("\n" + "=" * 50)
        print("📋 VALIDATION RESULTS:")

        if not self.issues and not self.warnings:
            print("🎉 All security checks passed!")
            return True

        if self.warnings:
            print("\n⚠️  WARNINGS:")
            for warning in self.warnings:
                print(f"  {warning}")

        if self.issues:
            print("\n❌ CRITICAL ISSUES:")
            for issue in self.issues:
                print(f"  {issue}")
            print("\n🚨 Please fix critical issues before deployment!")
            return False

        return True


def main():
    """Main function."""
    project_root = Path(__file__).parent.parent
    validator = SecurityValidator(project_root)

    success = validator.run_validation()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
