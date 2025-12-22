# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Integration with uv for dependency management
- Modern Python development tools:
  - ruff for linting and formatting
  - ty for type checking
  - pytest with coverage reporting
- GitHub Actions workflow for automated testing
- Docker development environment improvements
- Local CI testing with act for running GitHub Actions workflows locally
- Fast debug workflow for iterative development
- Make targets: `act-install`, `ci-list`, `ci-local`, `ci-local-docs`, `ci-debug`, `ci-clean`

### Changed
- Switched from pip/venv to uv for environment management
- Updated example code to pass ty type checking
- Modernized project structure and development workflow
- Updated Python version to 3.12

### Removed
- Legacy dependency management approach
- Outdated Docker configuration elements

### Fixed
- Type hints in example code to pass ty checks
- Docker environment management
- Development workflow and quality checks

## [0.1.0] - 2024-04-14
- Initial fork from eugeneyan/python-collab-template
- Added Docker environment management
- Setup package installation configuration
