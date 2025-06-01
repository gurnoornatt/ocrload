# 🚀 GitHub Actions CI Pipeline Setup

## Overview

This document explains your first GitHub Actions CI/CD pipeline for the OCR Load project. The pipeline is designed to be **beginner-friendly** while maintaining high code quality and security standards.

## 🎯 What the Pipeline Does

The CI pipeline automatically runs on every push to `main` or `develop` branches and every pull request. It performs:

1. **🔍 Code Quality Checks** - Linting and formatting
2. **🧪 Automated Testing** - Unit and integration tests
3. **🔒 Security Scanning** - Vulnerability and secrets detection
4. **🐳 Docker Building** - Container build and test
5. **🚀 Production Deploy** - Automatic deployment on main branch

## 📁 Files Created

### `.github/workflows/ci.yml`
The main CI pipeline configuration with 5 jobs:
- `lint` - Code quality and formatting checks
- `test` - Unit and integration tests (matrix strategy)
- `security` - Security scanning and secrets detection
- `build` - Docker image build and test
- `deploy` - Production image build and push (main branch only)

### `scripts/test_ci_locally.sh`
Local test script to validate CI components before pushing.

## 🛠 Pipeline Jobs Breakdown

### 1. Lint Job (`lint`)
**Purpose**: Ensure code quality and formatting consistency

**What it checks**:
- Essential Python syntax errors (Ruff E9, F63, F7, F82)
- Code formatting with Black (informational only)
- Basic format consistency with Ruff

**Beginner-friendly features**:
- Only fails on critical syntax errors
- Formatting issues are warnings, not failures
- Allows minor style inconsistencies initially

**How to fix issues**:
```bash
# Fix formatting
poetry run black .

# Fix critical linting issues
poetry run ruff check . --fix

# Check specific errors only
poetry run ruff check . --select=E9,F63,F7,F82
```

### 2. Test Job (`test`)
**Purpose**: Verify code functionality through automated tests

**Strategy**: Matrix testing with two parallel jobs:
- `unit` - Fast, isolated unit tests
- `integration` - Safe integration tests (no real API calls)

**Beginner-friendly features**:
- Tests continue even if some fail (`continue-on-error: true`)
- Uses placeholder credentials for safety
- Skips tests requiring real services initially

**Local testing**:
```bash
# Unit tests
poetry run pytest tests/unit/ -v

# Safe integration tests
poetry run pytest tests/integration/ -k "not real and not datalab and not redis" -v
```

### 3. Security Job (`security`)
**Purpose**: Scan for security vulnerabilities and secrets

**What it checks**:
- Python security issues with Bandit
- Hardcoded secrets detection
- Dependency vulnerabilities

**Features**:
- Uses your custom `validate_docker_security.py` script
- Scans for common security anti-patterns
- Validates no secrets are committed

### 4. Build Job (`build`)
**Purpose**: Test Docker container builds and functionality

**What it does**:
- Builds Docker image without pushing
- Tests container startup with placeholder env vars
- Verifies API endpoints are responsive
- Cleans up test containers

**Local testing**:
```bash
# Build and test Docker image
docker build -t ocrload:test .
docker run -d --name test -p 8000:8000 -e DEBUG=true ... ocrload:test
curl http://localhost:8000/health
```

### 5. Deploy Job (`deploy`)
**Purpose**: Build and push production images (main branch only)

**When it runs**:
- Only on pushes to `main` branch
- After all other jobs pass successfully

**What it does**:
- Logs into GitHub Container Registry (ghcr.io)
- Builds multi-architecture images
- Pushes with proper tags (latest, branch, SHA)
- Uses Docker layer caching for speed

## 🚦 Getting Started

### Step 1: Test Locally First
Before pushing to GitHub, test the CI components locally:

```bash
# Run the local CI test script
./scripts/test_ci_locally.sh
```

This script simulates what GitHub Actions will do and helps catch issues early.

### Step 2: Push to GitHub
Once local tests pass:

```bash
git add .
git commit -m "feat: Add GitHub Actions CI pipeline

- Implement lint, test, security, build, and deploy jobs
- Add local testing script
- Configure Docker image builds
- Set up automatic deployment on main branch"

git push origin main  # or your branch name
```

### Step 3: Monitor the Pipeline
1. Go to your GitHub repository
2. Click the **"Actions"** tab
3. Watch your pipeline run in real-time
4. Click on individual jobs to see detailed logs

## 🔧 Configuration

### Environment Variables
The pipeline uses placeholder values for testing, but you can add real secrets to GitHub:

1. Go to your repo → Settings → Secrets and variables → Actions
2. Add repository secrets for production deployments:
   - `SUPABASE_URL`
   - `SUPABASE_ANON_KEY`
   - `SUPABASE_SERVICE_KEY`
   - `DATALAB_API_KEY`
   - `REDIS_URL`
   - `redis_token`
   - `OPENAI_API_KEY`
   - `PERPLEXITY_API_KEY`

### Customizing the Pipeline

**To make linting stricter**:
```yaml
# In .github/workflows/ci.yml, change:
poetry run ruff check . --select=E9,F63,F7,F82
# To:
poetry run ruff check . --select=ALL
```

**To require all tests to pass**:
```yaml
# Remove this line from test steps:
continue-on-error: true
```

**To add more test types**:
```yaml
# Add to the matrix strategy:
strategy:
  matrix:
    test-type: ["unit", "integration", "e2e"]
```

## 🐛 Troubleshooting

### Common Issues

**1. Poetry/Python version conflicts**
```yaml
# Solution: The pipeline uses Python 3.12 by default
# If you need a different version, update:
env:
  PYTHON_VERSION: "3.11"  # or your preferred version
```

**2. Test failures**
- Check logs in GitHub Actions tab
- Run tests locally first: `poetry run pytest tests/unit/ -v`
- Tests are set to continue-on-error initially

**3. Docker build failures**
- Ensure Dockerfile is properly configured
- Test locally: `docker build -t test .`
- Check for missing dependencies in pyproject.toml

**4. Linting errors**
- Run locally: `poetry run ruff check . --fix`
- Format code: `poetry run black .`
- Only critical syntax errors will fail the pipeline initially

### Getting Help

**Pipeline not starting?**
- Check that your branch is `main` or `develop`
- Verify the `.github/workflows/ci.yml` file is committed
- Look for YAML syntax errors

**Jobs failing?**
- Click on the failed job in GitHub Actions
- Read the error logs
- Test the specific component locally
- Check the troubleshooting section above

**Docker issues?**
- Ensure all environment variables are provided
- Test with the same Docker command locally
- Check container logs: `docker logs <container-name>`

## 🎉 Success Indicators

When everything is working correctly, you'll see:

✅ **All CI checks passed!** 
- Lint job shows green checkmark
- Test jobs complete (even with some expected failures)
- Security scan passes 
- Docker build succeeds
- Deploy job runs on main branch

## 📈 Next Steps

After your first successful pipeline run:

1. **Gradually improve code quality**:
   - Fix linting issues over time
   - Increase test coverage
   - Remove `continue-on-error` flags

2. **Add more advanced features**:
   - Code coverage reporting
   - Performance testing
   - End-to-end tests with real services

3. **Set up notifications**:
   - Slack/Discord notifications
   - Email alerts for failures
   - Status badges in README

4. **Optimize for speed**:
   - Parallel job execution
   - Docker layer caching
   - Dependency caching

---

## 📚 Resources

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Docker Build Push Action](https://github.com/docker/build-push-action)
- [Poetry in CI/CD](https://python-poetry.org/docs/dependency-specification/)
- [Ruff Linting Rules](https://docs.astral.sh/ruff/rules/)

**Remember**: This is your first CI pipeline! It's designed to be forgiving while you learn. As you become more comfortable, you can make it stricter and add more advanced features.

🎊 **Congratulations on setting up your first GitHub Actions CI pipeline!** 🎊 