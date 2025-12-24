# Audio Capture Examples

Real-world examples of transcript events and conversation output from the voice capture pipeline.

## Overview

The audio capture pipeline produces `TranscriptEvent` objects that include:
- Speaker identification (Discord user ID)
- Transcribed text
- Audio chunk boundaries (milliseconds)
- Absolute timestamps (start/end)

This document shows what these events look like in different conversation scenarios.

## Data Structure

```python
@dataclass(frozen=True)
class TranscriptEvent:
    speaker_id: int         # Discord user_id
    chunk_id: str          # "{speaker_id}-{index}"
    text: str              # Transcribed text
    chunk: AudioChunk      # Audio boundaries (start_ms, end_ms)
    start_time: datetime   # Absolute timestamp
    end_time: datetime     # Absolute timestamp
```

---

## Scenario 1: Single Speaker Monologue

**Situation:** One person explaining a concept with natural pauses.

**Raw Events:**
```python
[
    TranscriptEvent(
        speaker_id=123456789,
        chunk_id='123456789-0',
        text='Hey everyone, thanks for joining the call.',
        chunk=AudioChunk(start_ms=0, end_ms=2100),
        start_time=datetime(2024, 1, 15, 14, 30, 0),
        end_time=datetime(2024, 1, 15, 14, 30, 2, 100000)
    ),
    TranscriptEvent(
        speaker_id=123456789,
        chunk_id='123456789-1',
        text='I wanted to discuss the new feature we shipped yesterday.',
        chunk=AudioChunk(start_ms=3200, end_ms=5800),
        start_time=datetime(2024, 1, 15, 14, 30, 3, 200000),
        end_time=datetime(2024, 1, 15, 14, 30, 5, 800000)
    ),
    TranscriptEvent(
        speaker_id=123456789,
        chunk_id='123456789-2',
        text='Overall the feedback has been really positive.',
        chunk=AudioChunk(start_ms=7000, end_ms=9200),
        start_time=datetime(2024, 1, 15, 14, 30, 7),
        end_time=datetime(2024, 1, 15, 14, 30, 9, 200000)
    )
]
```

**Formatted Output:**
```
[14:30:00] User#1234: Hey everyone, thanks for joining the call.
[14:30:03] User#1234: I wanted to discuss the new feature we shipped yesterday.
[14:30:07] User#1234: Overall the feedback has been really positive.
```

**Notes:**
- 3 utterances from single speaker
- Pauses at 2.1s → 3.2s (1.1s gap) and 5.8s → 7.0s (1.2s gap)
- Each pause exceeds `max_silence_ms` (500ms default) so split into separate utterances

---

## Scenario 2: Multi-Speaker Conversation

**Situation:** Three team members discussing API testing.

**Raw Events:**
```python
[
    TranscriptEvent(
        speaker_id=111111111,  # Alice
        chunk_id='111111111-0',
        text='Has anyone tested the new API endpoints yet?',
        chunk=AudioChunk(start_ms=0, end_ms=1800),
        start_time=datetime(2024, 1, 15, 14, 30, 0),
        end_time=datetime(2024, 1, 15, 14, 30, 1, 800000)
    ),
    TranscriptEvent(
        speaker_id=222222222,  # Bob
        chunk_id='222222222-0',
        text='Yeah, I ran through the test suite this morning.',
        chunk=AudioChunk(start_ms=0, end_ms=2100),
        start_time=datetime(2024, 1, 15, 14, 30, 2, 500000),
        end_time=datetime(2024, 1, 15, 14, 30, 4, 600000)
    ),
    TranscriptEvent(
        speaker_id=222222222,  # Bob continues
        chunk_id='222222222-1',
        text='Everything passed except for the auth timeout test.',
        chunk=AudioChunk(start_ms=2200, end_ms=4500),
        start_time=datetime(2024, 1, 15, 14, 30, 4, 700000),
        end_time=datetime(2024, 1, 15, 14, 30, 7, 200000)
    ),
    TranscriptEvent(
        speaker_id=333333333,  # Carol
        chunk_id='333333333-0',
        text='I can take a look at that timeout issue after lunch.',
        chunk=AudioChunk(start_ms=0, end_ms=2400),
        start_time=datetime(2024, 1, 15, 14, 30, 8),
        end_time=datetime(2024, 1, 15, 14, 30, 10, 400000)
    ),
    TranscriptEvent(
        speaker_id=111111111,  # Alice
        chunk_id='111111111-1',
        text='Thanks Carol, that would be great.',
        chunk=AudioChunk(start_ms=2000, end_ms=3200),
        start_time=datetime(2024, 1, 15, 14, 30, 11),
        end_time=datetime(2024, 1, 15, 14, 30, 12, 200000)
    )
]
```

**Formatted Output:**
```
[14:30:00] Alice: Has anyone tested the new API endpoints yet?
[14:30:02] Bob: Yeah, I ran through the test suite this morning.
[14:30:04] Bob: Everything passed except for the auth timeout test.
[14:30:08] Carol: I can take a look at that timeout issue after lunch.
[14:30:11] Alice: Thanks Carol, that would be great.
```

**Notes:**
- 5 events from 3 speakers
- Events automatically sorted chronologically across speakers
- Bob's utterances merged because gap (100ms) < max_silence_ms (500ms), then split as separate event

---

## Scenario 3: Overlapping/Interrupting Speakers

**Situation:** Bob interrupts Alice mid-sentence.

**Raw Events:**
```python
[
    TranscriptEvent(
        speaker_id=111111111,  # Alice starts
        chunk_id='111111111-0',
        text='I think we should probably consider migrating to the new',
        chunk=AudioChunk(start_ms=0, end_ms=2500),
        start_time=datetime(2024, 1, 15, 14, 30, 0),
        end_time=datetime(2024, 1, 15, 14, 30, 2, 500000)
    ),
    TranscriptEvent(
        speaker_id=222222222,  # Bob interrupts at 1.5s
        chunk_id='222222222-0',
        text='Wait, before we do that, did anyone check the migration docs?',
        chunk=AudioChunk(start_ms=0, end_ms=3200),
        start_time=datetime(2024, 1, 15, 14, 30, 1, 500000),  # Started during Alice
        end_time=datetime(2024, 1, 15, 14, 30, 4, 700000)
    ),
    TranscriptEvent(
        speaker_id=111111111,  # Alice continues after Bob
        chunk_id='111111111-1',
        text='database schema. But yeah, good point about the docs.',
        chunk=AudioChunk(start_ms=5000, end_ms=7500),
        start_time=datetime(2024, 1, 15, 14, 30, 5),
        end_time=datetime(2024, 1, 15, 14, 30, 7, 500000)
    )
]
```

**Formatted Output:**
```
[14:30:00.0] Alice: I think we should probably consider migrating to the new
[14:30:01.5] Bob: Wait, before we do that, did anyone check the migration docs?
[14:30:05.0] Alice: database schema. But yeah, good point about the docs.
```

**Notes:**
- Bob starts speaking while Alice is still talking (at 1.5s, Alice continues until 2.5s)
- Events maintain chronological order by start_time
- 1 second of overlapping speech (1.5s → 2.5s)
- Alice's sentence split across two events (interrupted)

---

## Scenario 4: Rapid Back-and-Forth

**Situation:** Quick deployment confirmation, speakers alternate every ~1 second.

**Raw Events:**
```python
[
    TranscriptEvent(speaker_id=111, chunk_id='111-0', text='Ready?',
                   start_time=datetime(2024, 1, 15, 14, 30, 0)),
    TranscriptEvent(speaker_id=222, chunk_id='222-0', text='Yep.',
                   start_time=datetime(2024, 1, 15, 14, 30, 0, 800000)),
    TranscriptEvent(speaker_id=111, chunk_id='111-1', text='Deploy it.',
                   start_time=datetime(2024, 1, 15, 14, 30, 1, 500000)),
    TranscriptEvent(speaker_id=222, chunk_id='222-1', text='On it.',
                   start_time=datetime(2024, 1, 15, 14, 30, 2, 200000)),
    TranscriptEvent(speaker_id=222, chunk_id='222-2', text='Deployed.',
                   start_time=datetime(2024, 1, 15, 14, 30, 8, 500000)),
    TranscriptEvent(speaker_id=111, chunk_id='111-2', text='Nice work.',
                   start_time=datetime(2024, 1, 15, 14, 30, 9)),
]
```

**Formatted Output:**
```
[14:30:00.0] User#111: Ready?
[14:30:00.8] User#222: Yep.
[14:30:01.5] User#111: Deploy it.
[14:30:02.2] User#222: On it.
[14:30:08.5] User#222: Deployed.
[14:30:09.0] User#111: Nice work.
```

**Notes:**
- Short utterances (< 1 second each)
- 6 second gap between "On it." and "Deployed." (deployment running)
- Events maintain sub-second precision for rapid exchanges

---

## Scenario 5: Silence Handling

**Situation:** Speaker pauses mid-sentence, then continues.

**Raw Events:**
```python
[
    TranscriptEvent(
        speaker_id=555,
        chunk_id='555-0',
        text='The first step is to update the config, then we need to',
        chunk=AudioChunk(start_ms=0, end_ms=3000),
        start_time=datetime(2024, 1, 15, 14, 30, 0),
        end_time=datetime(2024, 1, 15, 14, 30, 3)
    ),
    # 300ms pause - merged (< 500ms threshold)
    TranscriptEvent(
        speaker_id=555,
        chunk_id='555-0',  # Same chunk_id (merged utterance)
        text='restart the service and verify everything still works.',
        chunk=AudioChunk(start_ms=0, end_ms=5500),
        start_time=datetime(2024, 1, 15, 14, 30, 0),
        end_time=datetime(2024, 1, 15, 14, 30, 5, 500000)
    )
]
```

**Formatted Output:**
```
[14:30:00] User#555: The first step is to update the config, then we need to restart the service and verify everything still works.
```

**Notes:**
- Short pause (300ms) merged into single utterance
- If pause was > 500ms (max_silence_ms), would split into 2 events
- Whisper STT often bridges short pauses naturally

---

## Usage Examples

### Building a Conversation Transcript

```python
from datetime import datetime

# Get user display names from Discord
def get_user_name(speaker_id: int, guild) -> str:
    member = guild.get_member(speaker_id)
    return member.display_name if member else f"User#{speaker_id}"

# Format events as readable conversation
def format_transcript(events: list[TranscriptEvent], guild) -> str:
    lines = []
    for event in events:
        speaker = get_user_name(event.speaker_id, guild)
        timestamp = event.start_time.strftime("%H:%M:%S")
        lines.append(f"[{timestamp}] {speaker}: {event.text}")
    return "\n".join(lines)

# Usage
transcript = format_transcript(events, message.guild)
await message.channel.send(f"```\n{transcript}\n```")
```

**Output in Discord:**
```
[14:30:00] Alice: Has anyone tested the new API endpoints yet?
[14:30:02] Bob: Yeah, I ran through the test suite this morning.
[14:30:04] Bob: Everything passed except for the auth timeout test.
[14:30:08] Carol: I can take a look at that timeout issue after lunch.
[14:30:11] Alice: Thanks Carol, that would be great.
```

---

### Building LLM Context from Conversation

```python
from clanker.models import Context, Message, Persona

# Build conversation history for LLM
def build_conversation_context(
    events: list[TranscriptEvent],
    guild,
    request_context: Context
) -> Context:
    # Format as conversation
    transcript_lines = []
    for event in events:
        speaker = get_user_name(event.speaker_id, guild)
        transcript_lines.append(f"{speaker}: {event.text}")

    full_transcript = "\n".join(transcript_lines)

    # Create context for LLM
    return Context(
        request_id=request_context.request_id,
        user_id=request_context.user_id,
        guild_id=request_context.guild_id,
        channel_id=request_context.channel_id,
        persona=Persona(
            name="meeting-assistant",
            system_instruction="You are a helpful assistant that summarizes meetings."
        ),
        messages=[
            Message(
                role="user",
                content=f"Summarize this conversation:\n\n{full_transcript}"
            )
        ],
        metadata={
            "total_speakers": len(set(e.speaker_id for e in events)),
            "total_utterances": len(events),
            "duration_seconds": (events[-1].end_time - events[0].start_time).total_seconds()
        }
    )

# Send to LLM
llm_context = build_conversation_context(events, guild, base_context)
summary = await llm.generate(llm_context, llm_context.messages)
```

**LLM Output:**
```
The team discussed API testing progress. Bob reported that the test suite
mostly passed, but identified an auth timeout issue. Carol volunteered to
investigate the timeout problem after lunch, and Alice confirmed the plan.
```

---

### Filtering by Speaker

```python
# Get all events from specific speaker
def get_speaker_events(
    events: list[TranscriptEvent],
    speaker_id: int
) -> list[TranscriptEvent]:
    return [e for e in events if e.speaker_id == speaker_id]

# Example: Get everything Alice said
alice_events = get_speaker_events(events, speaker_id=111111111)
alice_text = " ".join(event.text for event in alice_events)
print(f"Alice said: {alice_text}")
```

**Output:**
```
Alice said: Has anyone tested the new API endpoints yet? Thanks Carol, that would be great.
```

---

### Searching Transcripts

```python
# Find events containing specific keywords
def search_events(
    events: list[TranscriptEvent],
    keywords: list[str]
) -> list[TranscriptEvent]:
    results = []
    for event in events:
        if any(keyword.lower() in event.text.lower() for keyword in keywords):
            results.append(event)
    return results

# Example: Find mentions of "API" or "test"
api_mentions = search_events(events, ["API", "test"])
for event in api_mentions:
    print(f"[{event.start_time}] {event.text}")
```

**Output:**
```
[2024-01-15 14:30:00] Has anyone tested the new API endpoints yet?
[2024-01-15 14:30:02] Yeah, I ran through the test suite this morning.
[2024-01-15 14:30:04] Everything passed except for the auth timeout test.
```

---

## Performance Characteristics

### Latency

From speech to transcript event:
- **VAD detection**: 50-100ms (Silero) or 10-20ms (Energy)
- **STT transcription**: 500-2000ms (depends on utterance length)
- **Total**: ~600-2100ms per utterance

### Ordering Guarantees

Events are **always sorted chronologically** by `start_time`:
- ✅ Events from different speakers maintain temporal order
- ✅ Simultaneous events (same start_time) sorted by speaker_id
- ✅ Events from same speaker maintain utterance order

### Memory Usage

Per speaker buffer:
- **Audio buffer**: ~192 KB per second (48kHz * 2 bytes * 2 seconds default)
- **TranscriptEvent**: ~200 bytes (includes strings)
- **10 speakers, 60 second conversation**: ~115 MB audio + ~60 KB events

---

## See Also

- [audio-capture.md](./audio-capture.md) - Full audio capture pipeline documentation
- [ARCHITECTURE.md](./ARCHITECTURE.md) - System architecture overview
- `tests/test_audio_scenarios.py` - E2E tests with scenario examples
- `src/clanker/voice/worker.py` - TranscriptEvent implementation
