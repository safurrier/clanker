# Clanker Configuration Schema

```yaml
providers:
  llm: openai
  stt: openai
  tts: elevenlabs
  image: memegen

default_persona: default

personas:
  - id: default
    display_name: Clanker
    system_prompt: "You are Clanker9000."
    tts_voice: null
    providers: {}
```

Notes:
- `providers` is required and selects a single provider per capability.
- `personas` must contain at least one persona.
- `default_persona` falls back to the first persona if omitted.
