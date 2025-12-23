#!/usr/bin/env python3
"""Validate meme template registry for correctness and quality."""

from __future__ import annotations

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from clanker.shitposts.memes import load_meme_templates


def validate_registry() -> list[str]:
    """Validate all templates in registry and return list of errors."""
    errors = []

    # Load all templates including disabled ones
    try:
        templates = load_meme_templates(include_nsfw=True, include_disabled=True)
    except Exception as e:
        return [f"Failed to load registry: {e}"]

    if not templates:
        return ["Registry is empty"]

    for template in templates:
        # Check required fields
        if not template.template_id:
            errors.append(f"{template.template_id}: Missing template_id")

        if not template.variant:
            errors.append(f"{template.template_id}: Missing variant name")

        if not template.variant_description:
            errors.append(
                f"{template.template_id}: Missing variant_description"
            )

        if not template.reference:
            errors.append(f"{template.template_id}: Missing reference URL")

        if not template.applicable_context:
            errors.append(
                f"{template.template_id}: Missing applicable_context"
            )

        # Check examples quality
        if not template.examples:
            errors.append(f"{template.template_id}: No examples provided")
        elif len(template.examples) < 3:
            errors.append(
                f"{template.template_id}: Only {len(template.examples)} examples "
                f"(minimum 3 recommended)"
            )

        # Check text_slots matches examples
        if template.examples:
            max_slots = max(len(ex) for ex in template.examples)
            if template.text_slots != max_slots:
                errors.append(
                    f"{template.template_id}: text_slots={template.text_slots} "
                    f"but max example length is {max_slots}"
                )

            # Check all examples have consistent slot count (warning, not error)
            slot_counts = {len(ex) for ex in template.examples}
            if len(slot_counts) > 2:
                errors.append(
                    f"{template.template_id}: Examples have inconsistent lengths "
                    f"{slot_counts} (some variation OK, but too many is suspicious)"
                )

            # Check for empty examples
            for i, example in enumerate(template.examples):
                if not example:
                    errors.append(
                        f"{template.template_id}: Example #{i} is empty"
                    )
                    continue
                # Check if all lines are blank
                try:
                    if all(
                        not str(line).strip() if isinstance(line, str) else False
                        for line in example
                    ):
                        errors.append(
                            f"{template.template_id}: Example #{i} has all blank lines"
                        )
                except Exception:
                    # Skip this check if example has unexpected structure
                    pass

        # Check disable reason is provided if disabled
        if template.do_not_use and not template.disable_reason:
            errors.append(
                f"{template.template_id}: Marked do_not_use=True but no "
                f"disable_reason provided"
            )

        # Check NSFW consistency
        if template.potentially_nsfw and not template.do_not_use:
            # This is OK - NSFW templates can still be used if explicitly enabled
            pass

    return errors


def main() -> None:
    """Run validation and exit with status code."""
    print("Validating meme template registry...")
    errors = validate_registry()

    if not errors:
        print("✓ Registry validation passed!")
        print(
            f"  {len(load_meme_templates(include_nsfw=True, include_disabled=True))} "
            f"templates total"
        )
        print(f"  {len(load_meme_templates())} templates enabled")
        sys.exit(0)
    else:
        print(f"✗ Found {len(errors)} validation errors:\n")
        for error in errors:
            print(f"  - {error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
