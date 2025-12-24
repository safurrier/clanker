"""
CLI tool for Clanker AI using Click.

This demonstrates reusing the core SDK in a command-line application.

Install:
    uv sync --extra cli

Usage:
    # Interactive chat mode
    clanker chat

    # One-off chat
    clanker chat "What is the meaning of life?"

    # Generate shitpost
    clanker shitpost

    # Generate shitpost with category
    clanker shitpost --category roast

    # List templates
    clanker templates

    # List personas
    clanker personas
"""

import asyncio
import sys
from functools import wraps
from pathlib import Path

import click

# Import core SDK - no Discord dependencies!
from clanker import Context, Message, Persona, respond
from clanker.config import load_personas
from clanker.providers import ProviderFactory
from clanker.providers.base import LLM, TTS
from clanker.shitposts import build_request, load_templates, render_shitpost, sample_template


# Click async support decorator
def async_command(f):
    """Decorator to support async Click commands."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        return asyncio.run(f(*args, **kwargs))
    return wrapper


# Global context for passing state between commands
class CLIContext:
    """Context object for CLI state."""

    def __init__(self):
        """Initialize CLI context."""
        self.llm: LLM | None = None
        self.tts: TTS | None = None
        self.personas: dict[str, Persona] = {}
        self.templates = []
        self.session_id = 0

    def initialize(self):
        """Initialize providers and load configuration."""
        if self.llm is not None:
            return  # Already initialized

        try:
            factory = ProviderFactory()
            self.llm = factory.get_llm("openai")
            self.tts = factory.get_tts("elevenlabs") if factory.has_tts() else None
            self.personas = load_personas()
            self.templates = load_templates()

            click.echo(click.style("✅ Clanker initialized", fg="green"))
            click.echo(f"   LLM: {type(self.llm).__name__}")
            click.echo(f"   TTS: {type(self.tts).__name__ if self.tts else 'None'}")
            click.echo(f"   Personas: {len(self.personas)}")
            click.echo(f"   Templates: {len(self.templates)}")
            click.echo()

        except Exception as e:
            click.echo(click.style(f"❌ Initialization failed: {e}", fg="red"), err=True)
            click.echo("\n💡 Make sure environment variables are set:", err=True)
            click.echo("   export OPENAI_API_KEY=your_key", err=True)
            sys.exit(1)

    def build_context(
        self,
        message_text: str,
        persona: Persona,
        user_id: str = "cli_user",
    ) -> Context:
        """
        Build SDK Context from CLI input.

        This is the adapter layer - converts CLI data into SDK's
        platform-agnostic Context.
        """
        import uuid

        return Context(
            request_id=str(uuid.uuid4()),
            user_id=int(hash(user_id)) % (2**31),
            guild_id=None,  # Not applicable for CLI
            channel_id=self.session_id,
            persona=persona,
            messages=[Message(role="user", content=message_text)],
            metadata={"source": "cli"},
        )


# Create Click group
@click.group()
@click.pass_context
def cli(ctx):
    """
    🤖 Clanker AI - Command-line interface for AI chat and shitpost generation.

    Built on the same SDK used by the Discord bot, demonstrating platform-agnostic reusability.
    """
    # Create CLI context and make it available to all commands
    ctx.ensure_object(CLIContext)


@cli.command()
@click.argument("message", required=False)
@click.option("--persona", "-p", default="default", help="Persona to use for chat")
@click.option("--interactive", "-i", is_flag=True, help="Start interactive chat mode")
@click.pass_obj
@async_command
async def chat(ctx: CLIContext, message: str | None, persona: str, interactive: bool):
    """
    Chat with an AI persona.

    Examples:
        clanker chat "What is Python?"
        clanker chat --persona shitposter "Tell me a joke"
        clanker chat --interactive
    """
    ctx.initialize()

    # Get persona
    persona_obj = ctx.personas.get(persona)
    if not persona_obj:
        click.echo(click.style(f"❌ Persona '{persona}' not found", fg="red"), err=True)
        click.echo(f"Available personas: {', '.join(ctx.personas.keys())}", err=True)
        return

    if interactive:
        await _interactive_chat(ctx, persona_obj)
    elif message:
        await _single_chat(ctx, message, persona_obj)
    else:
        click.echo(click.style("❌ Provide a message or use --interactive", fg="red"), err=True)
        click.echo("Example: clanker chat 'Hello!' or clanker chat --interactive", err=True)


async def _single_chat(ctx: CLIContext, message: str, persona: Persona):
    """Handle a single chat message."""
    try:
        # Build SDK context
        context = ctx.build_context(message, persona)

        # Use the same SDK function as Discord, web API, and WhatsApp bot!
        click.echo(click.style("🤔 Thinking...", fg="yellow"))
        reply, audio = await respond(context, ctx.llm, ctx.tts)

        # Output reply
        click.echo()
        click.echo(click.style(f"🤖 {persona.name}:", fg="cyan", bold=True))
        click.echo(reply.content)
        click.echo()

        if audio:
            click.echo(click.style("🔊 Audio generated (not played in CLI)", fg="green"))

    except Exception as e:
        click.echo(click.style(f"❌ Error: {e}", fg="red"), err=True)


async def _interactive_chat(ctx: CLIContext, persona: Persona):
    """Handle interactive chat mode."""
    click.echo(click.style(f"💬 Interactive chat with {persona.name}", fg="cyan", bold=True))
    click.echo(click.style("Type 'exit' or 'quit' to end the conversation\n", fg="yellow"))

    while True:
        try:
            # Get user input
            user_input = click.prompt(click.style("You", fg="green", bold=True), type=str)

            if user_input.lower() in ["exit", "quit", "bye"]:
                click.echo(click.style("👋 Goodbye!", fg="cyan"))
                break

            # Build SDK context
            context = ctx.build_context(user_input, persona)

            # Get response
            click.echo(click.style("🤔 Thinking...", fg="yellow"))
            reply, audio = await respond(context, ctx.llm, ctx.tts)

            # Output reply
            click.echo(click.style(f"\n🤖 {persona.name}:", fg="cyan", bold=True))
            click.echo(reply.content)
            click.echo()

        except (KeyboardInterrupt, EOFError):
            click.echo(click.style("\n👋 Goodbye!", fg="cyan"))
            break
        except Exception as e:
            click.echo(click.style(f"❌ Error: {e}", fg="red"), err=True)


@cli.command()
@click.option("--category", "-c", help="Template category (roast, advice, fact, etc.)")
@click.option("--template", "-t", help="Specific template name")
@click.option("--count", "-n", default=1, help="Number of shitposts to generate")
@click.pass_obj
@async_command
async def shitpost(ctx: CLIContext, category: str | None, template: str | None, count: int):
    """
    Generate shitposts using AI.

    Examples:
        clanker shitpost
        clanker shitpost --category roast
        clanker shitpost --template one_liner
        clanker shitpost --count 5
    """
    ctx.initialize()

    persona_obj = ctx.personas.get("shitposter", ctx.personas.get("default"))
    if not persona_obj:
        click.echo(click.style("❌ No persona available", fg="red"), err=True)
        return

    for i in range(count):
        try:
            # Sample template
            tmpl = sample_template(
                ctx.templates,
                category=category,
                name=template,
            )

            # Build request
            shitpost_request = build_request(tmpl)

            # Build SDK context
            context = ctx.build_context("", persona_obj)

            # Generate shitpost using SDK!
            click.echo(click.style("💩 Generating...", fg="yellow"))
            reply = await render_shitpost(context, ctx.llm, shitpost_request)

            # Output
            if count > 1:
                click.echo(click.style(f"\n[{i+1}/{count}]", fg="magenta"))
            click.echo(click.style("💩 " + reply.content, fg="green", bold=True))
            click.echo(click.style(f"   [{tmpl.name}]", fg="white", dim=True))
            click.echo()

        except Exception as e:
            click.echo(click.style(f"❌ Error: {e}", fg="red"), err=True)


@cli.command()
@click.pass_obj
def templates(ctx: CLIContext):
    """List available shitpost templates."""
    ctx.initialize()

    click.echo(click.style("📝 Available Templates\n", fg="cyan", bold=True))

    # Group by category
    categories = {}
    for tmpl in ctx.templates:
        if tmpl.category not in categories:
            categories[tmpl.category] = []
        categories[tmpl.category].append(tmpl)

    for cat, tmpls in sorted(categories.items()):
        click.echo(click.style(f"{cat.upper()}", fg="yellow", bold=True))
        for tmpl in tmpls:
            desc = f" - {tmpl.description}" if tmpl.description else ""
            click.echo(f"  • {tmpl.name}{desc}")
        click.echo()

    click.echo(click.style(f"Total: {len(ctx.templates)} templates", fg="white", dim=True))


@cli.command()
@click.pass_obj
def personas(ctx: CLIContext):
    """List available chat personas."""
    ctx.initialize()

    click.echo(click.style("🎭 Available Personas\n", fg="cyan", bold=True))

    for name, persona in ctx.personas.items():
        click.echo(click.style(f"{name}", fg="yellow", bold=True))
        # Show first 100 chars of personality
        personality = persona.personality[:100] + "..." if len(persona.personality) > 100 else persona.personality
        click.echo(f"  {personality}")
        click.echo()

    click.echo(click.style(f"Total: {len(ctx.personas)} personas", fg="white", dim=True))


@cli.command()
@click.pass_obj
def info(ctx: CLIContext):
    """Show Clanker SDK information."""
    ctx.initialize()

    click.echo(click.style("ℹ️  Clanker SDK Information\n", fg="cyan", bold=True))
    click.echo(f"LLM Provider: {type(ctx.llm).__name__}")
    click.echo(f"TTS Provider: {type(ctx.tts).__name__ if ctx.tts else 'Not configured'}")
    click.echo(f"Personas: {len(ctx.personas)}")
    click.echo(f"Templates: {len(ctx.templates)}")
    click.echo()
    click.echo(click.style("🔧 Configuration:", fg="yellow"))
    click.echo(f"   OPENAI_API_KEY: {'✅ Set' if ctx.llm else '❌ Not set'}")
    click.echo(f"   ELEVENLABS_API_KEY: {'✅ Set' if ctx.tts else '❌ Not set'}")


if __name__ == "__main__":
    cli(obj=CLIContext())
