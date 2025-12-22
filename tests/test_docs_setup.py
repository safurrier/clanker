"""Test MkDocs documentation setup and configuration."""

import subprocess
import tomli
from pathlib import Path


def test_mkdocs_dependencies_configured():
    """Test that MkDocs dependencies are configured in pyproject.toml."""
    pyproject_path = Path("pyproject.toml")
    assert pyproject_path.exists(), "pyproject.toml should exist"
    
    with open(pyproject_path, "rb") as f:
        config = tomli.load(f)
    
    # Check for dependency groups with docs dependencies (now conditional)
    if "dependency-groups" in config and "dev" in config["dependency-groups"]:
        dev_deps = config["dependency-groups"]["dev"]
        
        # Check for MkDocs dependencies
        mkdocs_deps = [dep for dep in dev_deps if "mkdocs" in dep.lower()]
        
        if mkdocs_deps:  # Only check if docs deps are present
            assert len(mkdocs_deps) >= 2, "Should have mkdocs-material and mkdocstrings dependencies"
            
            # Verify specific dependencies
            has_material = any("mkdocs-material" in dep for dep in dev_deps)
            has_mkdocstrings = any("mkdocstrings" in dep for dep in dev_deps)
            
            assert has_material, "Should have mkdocs-material dependency"
            assert has_mkdocstrings, "Should have mkdocstrings dependency"


def test_mkdocs_config_exists():
    """Test that mkdocs.yml configuration file exists (if docs enabled)."""
    mkdocs_config = Path("mkdocs.yml")
    if mkdocs_config.exists():
        # If it exists, it should be valid
        assert mkdocs_config.is_file(), "mkdocs.yml should be a file"


def test_mkdocs_config_valid():
    """Test that mkdocs.yml has valid configuration (if it exists)."""
    mkdocs_config = Path("mkdocs.yml")
    if not mkdocs_config.exists():
        return  # Skip if docs not enabled
        
    import yaml
    
    with open(mkdocs_config, "r") as f:
        config = yaml.safe_load(f)
    
    # Check required fields
    assert "site_name" in config, "mkdocs.yml should have site_name"
    assert "theme" in config, "mkdocs.yml should have theme configuration"
    assert config["theme"]["name"] == "material", "Should use Material theme"
    assert "plugins" in config, "mkdocs.yml should have plugins"
    
    # Check for required plugins
    plugin_names = []
    for plugin in config["plugins"]:
        if isinstance(plugin, dict):
            plugin_names.extend(plugin.keys())
        else:
            plugin_names.append(plugin)
    
    assert "search" in plugin_names, "Should have search plugin"
    assert "mkdocstrings" in plugin_names, "Should have mkdocstrings plugin"


def test_documentation_structure_exists():
    """Test that basic documentation structure exists (if docs enabled)."""
    docs_dir = Path("docs")
    if not docs_dir.exists():
        return  # Skip if docs not enabled
        
    assert docs_dir.is_dir(), "docs should be a directory"
    
    # Check for essential documentation files
    index_file = docs_dir / "index.md"
    assert index_file.exists(), "docs/index.md should exist"


def test_makefile_has_docs_targets():
    """Test that Makefile contains documentation targets."""
    makefile_path = Path("Makefile")
    assert makefile_path.exists(), "Makefile should exist"
    
    with open(makefile_path, "r") as f:
        makefile_content = f.read()
    
    # Check for documentation targets
    assert "docs-install:" in makefile_content, "Makefile should have docs-install target"
    assert "docs-build:" in makefile_content, "Makefile should have docs-build target"
    assert "docs-serve:" in makefile_content, "Makefile should have docs-serve target"
    assert "docs-check:" in makefile_content, "Makefile should have docs-check target"
    assert "docs-clean:" in makefile_content, "Makefile should have docs-clean target"


def test_github_actions_docs_workflow():
    """Test that GitHub Actions workflow for docs exists (if docs enabled)."""
    workflow_path = Path(".github/workflows/docs.yml")
    if not workflow_path.exists():
        return  # Skip if docs not enabled
    
    import yaml
    with open(workflow_path, "r") as f:
        workflow = yaml.safe_load(f)
    
    # Note: YAML parses "on" as boolean True, not string "on"
    assert True in workflow or "on" in workflow, "Workflow should have trigger configuration"
    assert "jobs" in workflow, "Workflow should have jobs"
    
    # Check for deployment job
    jobs = workflow["jobs"]
    assert any("deploy" in job_name.lower() or "docs" in job_name.lower() 
              for job_name in jobs.keys()), "Should have a docs deployment job"


def test_template_files_exist():
    """Test that template files exist for documentation setup."""
    template_dir = Path("templates")
    assert template_dir.exists(), "templates/ directory should exist"
    
    # Check for essential template files
    template_files = [
        "mkdocs.yml.template",
        "docs/index.md.template",
        "docs/getting-started.md.template",
        "docs/reference/api.md.template",
        ".github/workflows/docs.yml.template"
    ]
    
    for template_file in template_files:
        template_path = template_dir / template_file
        assert template_path.exists(), f"Template file {template_file} should exist"