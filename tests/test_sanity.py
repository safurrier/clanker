"""Sanity tests."""

from clanker import Context, Message, Persona


def test_imports() -> None:
    persona = Persona(id="id", display_name="name", system_prompt="prompt")
    context = Context(
        request_id="req",
        user_id=1,
        guild_id=None,
        channel_id=2,
        persona=persona,
        messages=[Message(role="user", content="hi")],
        metadata={},
    )
    assert context.persona.display_name == "name"
