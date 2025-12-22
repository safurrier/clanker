import os
import subprocess
import sys
from pathlib import Path
from typing import Optional
import tomli
import tomli_w


def prompt_with_default(prompt: str, default: str) -> str:
    """Prompt for input with a default value."""
    response = input(f"{prompt} [{default}]: ").strip()
    return response if response else default


def get_git_config(key: str) -> Optional[str]:
    """Get git config value."""
    try:
        return subprocess.check_output(
            ["git", "config", "user."+key], text=True
        ).strip()
    except subprocess.CalledProcessError:
        return None


def update_pyproject_toml(
    project_name: str,
    project_description: str,
    author_name: str,
    author_email: str
) -> None:
    """Update pyproject.toml with new project information."""
    pyproject_path = Path("pyproject.toml")
    
    # Read existing toml
    with open(pyproject_path, "rb") as f:
        config = tomli.load(f)
    
    # Update project information
    config["project"]["name"] = project_name
    config["project"]["description"] = project_description
    config["project"]["authors"] = [
        {"name": author_name, "email": author_email}
    ]
    
    # Write updated toml
    with open(pyproject_path, "wb") as f:
        tomli_w.dump(config, f)


def run_command(command: str) -> None:
    """Run a shell command and exit if it fails."""
    try:
        subprocess.run(command, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {command}")
        print(f"Error: {e}")
        sys.exit(1)


def template_file(template_path: str, output_path: str, replacements: dict) -> None:
    """Template a file by replacing placeholders with values."""
    with open(template_path, "r") as f:
        content = f.read()
    
    for placeholder, value in replacements.items():
        content = content.replace(f"{{{placeholder}}}", value)
    
    # Ensure parent directory exists (only if there is a parent directory)
    parent_dir = os.path.dirname(output_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
    
    with open(output_path, "w") as f:
        f.write(content)


def setup_documentation(
    project_name: str,
    project_description: str,
    author_name: str,
    author_email: str,
    project_module_name: str,
    github_username: str = "your-username"
) -> None:
    """Set up documentation with MkDocs + Material theme."""
    print("📚 Setting up documentation...")
    
    # Define template replacements
    replacements = {
        "project_name": project_name,
        "project_description": project_description,
        "author_name": author_name,
        "author_email": author_email,
        "project_module_name": project_module_name,
        "github_username": github_username,
    }
    
    # Template and create documentation files
    template_file("templates/mkdocs.yml.template", "mkdocs.yml", replacements)
    template_file("templates/docs/index.md.template", "docs/index.md", replacements)
    template_file("templates/docs/getting-started.md.template", "docs/getting-started.md", replacements)
    template_file("templates/docs/reference/api.md.template", "docs/reference/api.md", replacements)
    template_file("templates/.github/workflows/docs.yml.template", ".github/workflows/docs.yml", replacements)
    
    # Add documentation dependencies to pyproject.toml
    pyproject_path = Path("pyproject.toml")
    with open(pyproject_path, "rb") as f:
        config = tomli.load(f)
    
    # Ensure dependency-groups exists
    if "dependency-groups" not in config:
        config["dependency-groups"] = {}
    
    # Add docs dependencies to dev group
    if "dev" not in config["dependency-groups"]:
        config["dependency-groups"]["dev"] = []
    
    docs_deps = [
        "mkdocs-material>=9.6.14",
        "mkdocstrings[python]>=0.26.1",
    ]
    
    for dep in docs_deps:
        if dep not in config["dependency-groups"]["dev"]:
            config["dependency-groups"]["dev"].append(dep)
    
    with open(pyproject_path, "wb") as f:
        tomli_w.dump(config, f)
    
    print("✅ Documentation setup complete")
    print("   - MkDocs configuration created")
    print("   - Documentation structure created")
    print("   - GitHub Actions workflow added")
    print("   - Dependencies added to pyproject.toml")


def main() -> None:
    print("🚀 Initializing new Python project...")

    # Get project information
    project_name = prompt_with_default(
        "Project name", "my-python-project"
    )
    project_description = prompt_with_default(
        "Project description", "A Python project"
    )
    author_name = prompt_with_default(
        "Author name", get_git_config("name") or "Your Name"
    )
    author_email = prompt_with_default(
        "Author email", get_git_config("email") or "your.email@example.com"
    )

    # Update project information
    print("📝 Updating project configuration...")
    update_pyproject_toml(
        project_name,
        project_description,
        author_name,
        author_email
    )

    # Handle example code
    code_choice = prompt_with_default(
        "How would you like to handle example code?\n"
        "1. Keep example code (useful for reference)\n"
        "2. Create minimal placeholder test (ensures checks pass)\n"
        "3. Remove all example code (clean slate)\n"
        "Choose option (1/2/3)", "1"
    )

    # Create module directory with project name (replacing src)
    project_module_name = project_name.replace("-", "_").lower()
    
    # Always update the Makefile to use the new module name
    print(f"🔧 Updating Makefile to use module name: {project_module_name}")
    makefile_path = Path("Makefile")
    with open(makefile_path, "r") as f:
        makefile_content = f.read()
    
    # Replace module name in Makefile
    updated_makefile = makefile_content.replace("MODULE_NAME := src", f"MODULE_NAME := {project_module_name}")
    
    with open(makefile_path, "w") as f:
        f.write(updated_makefile)
    
    # Always update pyproject.toml to point to the new module directory
    print(f"📦 Updating pyproject.toml for module: {project_module_name}")
    pyproject_path = Path("pyproject.toml")
    with open(pyproject_path, "rb") as f:
        config = tomli.load(f)
    
    # Update packages from src to new module name
    if "tool" in config and "hatch" in config["tool"] and "build" in config["tool"]["hatch"] and "targets" in config["tool"]["hatch"]["build"] and "wheel" in config["tool"]["hatch"]["build"]["targets"]:
        config["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"] = [project_module_name]
    
    # Update ruff known-first-party if ruff config exists
    if "tool" in config and "ruff" in config["tool"] and "lint" in config["tool"]["ruff"] and "isort" in config["tool"]["ruff"]["lint"]:
        config["tool"]["ruff"]["lint"]["isort"]["known-first-party"] = [project_module_name]
    
    with open(pyproject_path, "wb") as f:
        tomli_w.dump(config, f)
    
    # Create the new module directory if it doesn't exist
    if not os.path.exists(project_module_name):
        print(f"📁 Creating module directory: {project_module_name}")
        os.mkdir(project_module_name)
        # Create __init__.py
        with open(f"{project_module_name}/__init__.py", "w") as f:
            f.write(f'"""Main package for {project_name}."""\n')
    
    # Copy src content to new module directory if src exists
    if os.path.exists("src") and project_module_name != "src":
        print(f"📦 Copying content from src to {project_module_name}...")
        for item in os.listdir("src"):
            src_path = os.path.join("src", item)
            dest_path = os.path.join(project_module_name, item)
            
            if os.path.isfile(src_path):
                with open(src_path, "r") as src_file:
                    content = src_file.read()
                with open(dest_path, "w") as dest_file:
                    dest_file.write(content)
        
        # Remove the old src directory after copying
        print("🗑️ Removing old src directory...")
        run_command("rm -rf src")
    
    if code_choice == "2":
        print("📝 Creating minimal placeholder test...")
        # Create minimal module
        with open(f"{project_module_name}/example.py", "w") as f:
            f.write("""def add(a: int, b: int) -> int:
    \"\"\"Add two numbers.\"\"\"
    return a + b
""")
        
        # Create minimal test
        with open("tests/test_example.py", "w") as f:
            f.write(f"""from {project_module_name}.example import add

def test_add():
    assert add(1, 2) == 3
""")
    elif code_choice == "3":
        print("🧹 Removing all example code...")
        run_command("make clean-example")
        # Create __init__.py in tests
        with open("tests/__init__.py", "w") as f:
            f.write("")
    else:
        print("📚 Updating example code imports for new module name...")
        # Update example.py to use new module name
        if os.path.exists("src/example.py"):
            with open("src/example.py", "r") as f:
                example_content = f.read()
            # Save it to new module directory
            with open(f"{project_module_name}/example.py", "w") as f:
                f.write(example_content)
        
        # Update test imports 
        if os.path.exists("tests/test_example.py"):
            with open("tests/test_example.py", "r") as f:
                test_content = f.read()
            updated_test = test_content.replace("from src.", f"from {project_module_name}.")
            with open("tests/test_example.py", "w") as f:
                f.write(updated_test)

    # Documentation setup
    docs_choice = prompt_with_default(
        "\nWould you like to set up documentation with MkDocs?\n"
        "This includes:\n"
        "- Material theme documentation site\n"
        "- Auto-generated API documentation\n"
        "- GitHub Pages deployment\n"
        "- Local development server\n"
        "\nSet up documentation? (Y/n)", "y"
    )
    
    docs_enabled = docs_choice.lower() in ('y', 'yes', '')
    if docs_enabled:
        # Extract GitHub username from git config or use placeholder
        try:
            github_url = subprocess.check_output(["git", "config", "remote.origin.url"], text=True).strip()
            if "github.com" in github_url:
                # Extract username from GitHub URL
                if github_url.startswith("git@github.com:"):
                    github_username = github_url.split(":")[1].split("/")[0]
                elif github_url.startswith("https://github.com/"):
                    github_username = github_url.split("/")[3]
                else:
                    github_username = "your-username"
            else:
                github_username = "your-username"
        except (subprocess.CalledProcessError, IndexError):
            github_username = "your-username"
        
        setup_documentation(
            project_name,
            project_description,
            author_name,
            author_email,
            project_module_name,
            github_username
        )
    else:
        print("⏩ Skipping documentation setup")

    # Get current directory name and handle renaming
    current_dir = os.path.basename(os.getcwd())
    if current_dir == "python-collab-template" or current_dir == "python-project-test":
        parent_dir = os.path.dirname(os.getcwd())
        new_dir = os.path.join(parent_dir, project_name)
        print(f"📁 Renaming project directory to {project_name}...")
        if os.path.exists(new_dir):
            print(f"⚠️  Directory {project_name} already exists. Keeping current directory name.")
        else:
            # Update source code directory references in Makefile
            makefile_path = Path("Makefile")
            with open(makefile_path, "r") as f:
                makefile_content = f.read()
            
            # Replace any hardcoded references to python-collab-template in the Makefile
            updated_makefile = makefile_content.replace("python-collab-template", project_name)
            
            with open(makefile_path, "w") as f:
                f.write(updated_makefile)
                
            # Now rename the directory
            os.chdir(parent_dir)
            os.rename(current_dir, project_name)
            os.chdir(project_name)

    # Install dependencies and set up environment
    print("🔨 Setting up development environment...")
    run_command("make setup")

    # Configure pre-commit hooks
    precommit_choice = prompt_with_default(
        "\nWould you like to enable pre-commit hooks?\n"
        "These hooks run automatically before each commit to ensure code quality:\n"
        "- Type checking (ty)\n"
        "- Linting (ruff)\n"
        "- Formatting (ruff)\n"
        "- Tests (pytest)\n"
        "\nEnable pre-commit hooks? (y/n)", "y"
    )
    
    # Initialize new git repository
    print("🔄 Initializing git repository...")
    if os.path.exists(".git"):
        run_command("rm -rf .git")
    run_command("git init")
    
    if precommit_choice.lower() in ('y', 'yes'):
        print("🔧 Setting up pre-commit hooks...")
        run_command("uv run pre-commit install")
    else:
        print("⏩ Skipping pre-commit hooks setup")

    # Initial commit without running pre-commit hooks
    run_command("git add .")
    run_command('git commit -m "feat: Initial project setup" --no-verify')

    print("✨ Project initialized successfully!")
    next_steps = [
        "1. Update README.md with your project details",
        "2. Review and update CHANGELOG.md", 
        f"3. Start adding your code in {project_module_name}/",
        "4. Run 'make check' to verify everything works"
    ]
    
    if docs_enabled:
        next_steps.extend([
            "5. Serve documentation locally: 'make docs-serve'",
            "6. Update docs content in docs/ directory",
            "7. Enable GitHub Pages in repository settings for automatic deployment"
        ])
    
    print("\nNext steps:")
    for step in next_steps:
        print(step)
    
    print("\nHappy coding! 🎉")


if __name__ == "__main__":
    main()
