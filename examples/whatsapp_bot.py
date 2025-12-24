"""
WhatsApp bot using Twilio API and Flask.

This demonstrates reusing the core SDK in a WhatsApp bot without Discord dependencies.

Setup:
1. Install dependencies: uv sync --extra whatsapp
2. Set environment variables:
   - TWILIO_ACCOUNT_SID
   - TWILIO_AUTH_TOKEN
   - OPENAI_API_KEY
   - ELEVENLABS_API_KEY (optional)
3. Run: uv run python examples/whatsapp_bot.py
4. Use ngrok for local development: ngrok http 5000
5. Configure Twilio webhook to your ngrok URL + /webhook

For production deployment, use a proper web server (gunicorn, AWS, Heroku, etc.)
"""

import logging
import os
import uuid
from contextlib import asynccontextmanager

from flask import Flask, request
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse

# Import core SDK - no Discord dependencies!
from clanker import Context, Message, Persona, respond
from clanker.config import load_personas
from clanker.providers import ProviderFactory
from clanker.providers.base import LLM, TTS
from clanker.shitposts import build_request, load_templates, render_shitpost, sample_template

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WhatsAppBot:
    """WhatsApp bot that reuses the core Clanker SDK."""

    def __init__(self):
        """Initialize the bot with providers and Twilio client."""
        # Initialize SDK providers (same as Discord bot)
        factory = ProviderFactory()
        self.llm: LLM = factory.get_llm("openai")
        self.tts: TTS | None = factory.get_tts("elevenlabs") if factory.has_tts() else None
        self.personas: dict[str, Persona] = load_personas()
        self.templates = load_templates()

        # Initialize Twilio client
        account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
        auth_token = os.environ.get("TWILIO_AUTH_TOKEN")

        if not account_sid or not auth_token:
            logger.warning("⚠️  Twilio credentials not set - webhook will work but can't send proactive messages")
            self.twilio_client = None
        else:
            self.twilio_client = Client(account_sid, auth_token)

        logger.info("✅ WhatsApp bot initialized")
        logger.info(f"   - LLM: {type(self.llm).__name__}")
        logger.info(f"   - TTS: {type(self.tts).__name__ if self.tts else 'None'}")
        logger.info(f"   - Personas: {len(self.personas)}")
        logger.info(f"   - Templates: {len(self.templates)}")

    def build_context(
        self,
        user_id: str,
        message_text: str,
        persona: Persona,
    ) -> Context:
        """
        Build SDK Context from WhatsApp message.

        This is the adapter layer - converts WhatsApp data into SDK's
        platform-agnostic Context.
        """
        return Context(
            request_id=str(uuid.uuid4()),
            user_id=int(hash(user_id)) % (2**31),  # Convert phone number to int ID
            guild_id=None,  # Not applicable for WhatsApp
            channel_id=int(hash(user_id)) % (2**31),  # Use user_id as "channel"
            persona=persona,
            messages=[Message(role="user", content=message_text)],
            metadata={
                "source": "whatsapp",
                "phone": user_id,
            },
        )

    async def handle_message(self, from_number: str, message_text: str) -> str:
        """
        Handle incoming WhatsApp message.

        Routes to either shitpost generation or chat based on command.
        """
        message_lower = message_text.lower().strip()

        # Command routing
        if message_lower.startswith("/shitpost") or message_lower.startswith("!shitpost"):
            return await self._handle_shitpost(from_number, message_text)
        elif message_lower.startswith("/help") or message_lower == "help":
            return self._handle_help()
        elif message_lower.startswith("/templates") or message_lower == "templates":
            return self._handle_templates()
        else:
            # Default: chat
            return await self._handle_chat(from_number, message_text)

    async def _handle_chat(self, from_number: str, message_text: str) -> str:
        """Handle chat using the SDK's respond() function."""
        try:
            persona = self.personas.get("default")
            if not persona:
                return "❌ No persona configured"

            # Build SDK context
            context = self.build_context(from_number, message_text, persona)

            # Use the same SDK function as Discord and web API!
            reply, audio = await respond(context, self.llm, self.tts)

            return reply.content

        except Exception as e:
            logger.error(f"Error in chat: {e}", exc_info=True)
            return f"❌ Sorry, I encountered an error: {str(e)}"

    async def _handle_shitpost(self, from_number: str, message_text: str) -> str:
        """Handle shitpost generation using the SDK's shitpost pipeline."""
        try:
            # Parse command: /shitpost [category] or /shitpost [template_name]
            parts = message_text.split(maxsplit=1)
            category = None
            template_name = None

            if len(parts) > 1:
                arg = parts[1].strip()
                # Try as category first
                categories = {t.category for t in self.templates}
                if arg in categories:
                    category = arg
                else:
                    # Try as template name
                    template_name = arg

            # Sample template
            template = sample_template(
                self.templates,
                category=category,
                name=template_name,
            )

            # Build request
            shitpost_request = build_request(template)

            # Build SDK context
            persona = self.personas.get("shitposter", self.personas.get("default"))
            if not persona:
                return "❌ No persona configured"

            context = self.build_context(from_number, "", persona)

            # Generate shitpost using SDK!
            reply = await render_shitpost(context, self.llm, shitpost_request)

            return f"💩 {reply.content}\n\n_[{template.name}]_"

        except Exception as e:
            logger.error(f"Error generating shitpost: {e}", exc_info=True)
            return f"❌ Sorry, I couldn't generate a shitpost: {str(e)}"

    def _handle_help(self) -> str:
        """Return help message."""
        return """🤖 *Clanker WhatsApp Bot*

*Commands:*
• Just chat with me normally for AI conversation
• `/shitpost` - Generate a random shitpost
• `/shitpost [category]` - Generate shitpost in category
• `/templates` - List available templates
• `/help` - Show this help

*Categories:* roast, advice, fact, one_liner

*Example:*
`/shitpost roast`
"""

    def _handle_templates(self) -> str:
        """Return list of templates."""
        categories = {}
        for template in self.templates:
            if template.category not in categories:
                categories[template.category] = []
            categories[template.category].append(template.name)

        result = "📝 *Available Templates*\n\n"
        for category, names in sorted(categories.items()):
            result += f"*{category.upper()}*\n"
            for name in names:
                result += f"  • {name}\n"
            result += "\n"

        result += "Use: `/shitpost [category]` or `/shitpost [name]`"
        return result


# Create Flask app
app = Flask(__name__)
bot: WhatsAppBot | None = None


@app.before_request
def initialize_bot():
    """Initialize bot on first request (lazy loading)."""
    global bot
    if bot is None:
        bot = WhatsAppBot()


@app.route("/webhook", methods=["POST"])
def webhook():
    """
    Twilio webhook endpoint.

    This receives incoming WhatsApp messages and sends responses.
    """
    try:
        # Get incoming message details
        from_number = request.form.get("From", "")  # Format: whatsapp:+1234567890
        message_text = request.form.get("Body", "")

        logger.info(f"📨 Received message from {from_number}: {message_text}")

        # Handle message asynchronously
        import asyncio
        reply_text = asyncio.run(bot.handle_message(from_number, message_text))

        # Create TwiML response
        response = MessagingResponse()
        response.message(reply_text)

        logger.info(f"📤 Sending reply: {reply_text[:100]}...")

        return str(response)

    except Exception as e:
        logger.error(f"Error in webhook: {e}", exc_info=True)
        response = MessagingResponse()
        response.message("❌ Sorry, something went wrong. Please try again.")
        return str(response)


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "Clanker WhatsApp Bot",
        "providers": {
            "llm": type(bot.llm).__name__ if bot else None,
            "tts": type(bot.tts).__name__ if bot and bot.tts else None,
        },
    }


@app.route("/", methods=["GET"])
def home():
    """Home endpoint with setup instructions."""
    return """
    <h1>🤖 Clanker WhatsApp Bot</h1>
    <p>This bot is running and ready to receive messages!</p>
    <h2>Setup Instructions:</h2>
    <ol>
        <li>Configure Twilio sandbox: <a href="https://www.twilio.com/console/sms/whatsapp/sandbox">Twilio WhatsApp Sandbox</a></li>
        <li>Set webhook URL to: <code>https://your-domain.com/webhook</code></li>
        <li>Send a message to your Twilio WhatsApp number</li>
    </ol>
    <h2>Commands:</h2>
    <ul>
        <li>Chat normally for AI conversation</li>
        <li><code>/shitpost</code> - Generate random shitpost</li>
        <li><code>/help</code> - Show help</li>
        <li><code>/templates</code> - List templates</li>
    </ul>
    """


if __name__ == "__main__":
    # For development only - use gunicorn/uwsgi for production
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"🚀 Starting WhatsApp bot on port {port}")
    logger.info(f"📱 Webhook endpoint: http://localhost:{port}/webhook")
    logger.info(f"💡 Use ngrok for local development: ngrok http {port}")
    app.run(host="0.0.0.0", port=port, debug=True)
