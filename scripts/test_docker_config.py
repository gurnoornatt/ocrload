#!/usr/bin/env python3
"""
Docker Configuration Test Script
Tests Docker configuration files for correctness without requiring Docker to be running.
"""

import sys
from pathlib import Path


def test_dockerfile_syntax():
    """Test Dockerfile syntax and structure."""
    dockerfile_path = Path(__file__).parent.parent / "Dockerfile"

    if not dockerfile_path.exists():
        print("❌ Dockerfile not found")
        return False

    content = dockerfile_path.read_text()

    # Check for required elements
    checks = [
        ("FROM", "Multi-stage build with FROM statements"),
        ("USER appuser", "Non-root user configuration"),
        ("HEALTHCHECK", "Health check configuration"),
        ("EXPOSE", "Port exposure"),
        ("CMD", "Container startup command"),
        ("WORKDIR", "Working directory set"),
        ("COPY --chown=appuser:appuser", "Proper file ownership"),
    ]

    all_passed = True
    for check, description in checks:
        if check in content:
            print(f"✅ {description}")
        else:
            print(f"❌ Missing: {description}")
            all_passed = False

    return all_passed


def test_dockerignore():
    """Test .dockerignore file."""
    dockerignore_path = Path(__file__).parent.parent / ".dockerignore"

    if not dockerignore_path.exists():
        print("❌ .dockerignore not found")
        return False

    content = dockerignore_path.read_text()

    # Check for security-critical exclusions
    critical_exclusions = [".env", ".cursor/", "tests/", "*.log", "__pycache__/"]

    all_passed = True
    for exclusion in critical_exclusions:
        if exclusion in content:
            print(f"✅ .dockerignore excludes: {exclusion}")
        else:
            print(f"❌ .dockerignore missing: {exclusion}")
            all_passed = False

    return all_passed


def test_docker_compose():
    """Test docker-compose configuration."""
    compose_path = Path(__file__).parent.parent / "docker-compose.yml"

    if not compose_path.exists():
        print("❌ docker-compose.yml not found")
        return False

    content = compose_path.read_text()

    # Check for required elements
    checks = [
        ("version:", "Docker Compose version specified"),
        ("services:", "Services section defined"),
        ("healthcheck:", "Health check configured"),
        ("environment:", "Environment variables configured"),
        ("networks:", "Networks configured"),
        ("restart: unless-stopped", "Restart policy configured"),
    ]

    all_passed = True
    for check, description in checks:
        if check in content:
            print(f"✅ {description}")
        else:
            print(f"❌ Missing: {description}")
            all_passed = False

    return all_passed


def test_environment_template():
    """Test .env.example file."""
    env_example_path = Path(__file__).parent.parent / ".env.example"

    if not env_example_path.exists():
        print("❌ .env.example not found")
        return False

    content = env_example_path.read_text()

    # Check for required environment variables
    required_vars = [
        "SUPABASE_URL",
        "SUPABASE_SERVICE_KEY",
        "DATALAB_API_KEY",
        "ENVIRONMENT",
        "PORT",
    ]

    all_passed = True
    for var in required_vars:
        if var in content:
            print(f"✅ Environment template includes: {var}")
        else:
            print(f"❌ Missing environment variable: {var}")
            all_passed = False

    return all_passed


def main():
    """Run all Docker configuration tests."""
    print("🐳 Testing Docker Configuration...")
    print("=" * 50)

    tests = [
        ("Dockerfile Syntax", test_dockerfile_syntax),
        ("Dockerignore", test_dockerignore),
        ("Docker Compose", test_docker_compose),
        ("Environment Template", test_environment_template),
    ]

    all_passed = True
    for test_name, test_func in tests:
        print(f"\n📋 {test_name}:")
        if not test_func():
            all_passed = False

    print("\n" + "=" * 50)
    if all_passed:
        print("🎉 All Docker configuration tests passed!")
        print("✅ Ready for deployment!")
    else:
        print("❌ Some Docker configuration tests failed!")
        print("🚨 Please fix issues before deployment!")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
