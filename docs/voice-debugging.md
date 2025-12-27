# Voice Pipeline Debugging

Tools and techniques for diagnosing voice transcription quality issues.

## Quick Start

```bash
# Enable debug capture and verbose logging
LOG_LEVEL=DEBUG VOICE_DEBUG=1 python -m clanker_bot

# Or with Docker
docker-compose -f docker/docker-compose.prod.yml up \
  -e LOG_LEVEL=DEBUG -e VOICE_DEBUG=1
```

## Debug Capture System

When `VOICE_DEBUG=1` is set, the pipeline saves all intermediate stages to disk for offline analysis.

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VOICE_DEBUG` | (disabled) | Set to `1` to enable capture |
| `VOICE_DEBUG_DIR` | `./voice_debug` | Output directory |
| `LOG_LEVEL` | `INFO` | Set to `DEBUG` for verbose pipeline logs |

### Output Structure

Each processing cycle creates a session directory:

```
voice_debug/
  session_2024-01-15_14-30-22_abc123/
    manifest.json           # Complete metadata + config
    transcript.txt          # Human-readable transcript

    users/
      {user_id}/
        raw_buffer.pcm      # Full PCM buffer (48kHz)
        raw_buffer.wav      # Playable WAV version
        vad_segments.json   # Detected speech segments

        utterances/
          {index}/
            audio_48000hz.wav   # Original sample rate
            audio_16khz.wav     # Resampled for Whisper
            stt_result.json     # Transcription result
```

### Analyzing Sessions

Use the analysis script to review captured sessions:

```bash
# Analyze all sessions
python scripts/analyze_voice_session.py voice_debug/session_*/

# Analyze specific session
python scripts/analyze_voice_session.py voice_debug/session_2024-01-15_14-30-22_abc123/

# JSON output for scripting
python scripts/analyze_voice_session.py --json voice_debug/session_*/
```

The analyzer reports:
- Sample rate configuration
- VAD coverage (% of audio detected as speech)
- Empty/short transcriptions
- STT latency statistics
- Filtered utterances count

### Manual Audio Inspection

Play back captured audio to compare with transcriptions and isolate issues:

```bash
# 1. First, check the raw buffer (full capture from Discord)
afplay voice_debug/session_*/users/*/raw_buffer.wav

# 2. If raw sounds wrong (slow/distorted), issue is in Discord capture
#    If raw sounds fine, continue to check utterances...

# 3. Play the sliced utterance at original 48kHz
afplay voice_debug/session_*/users/*/utterances/0/audio_48000hz.wav

# 4. Play the resampled 16kHz version (what Whisper receives)
afplay voice_debug/session_*/users/*/utterances/0/audio_16khz.wav

# 5. Check what Whisper returned
cat voice_debug/session_*/users/*/utterances/0/stt_result.json
```

**Debugging flow:**

```
raw_buffer.wav sounds wrong?
    └─> Yes: Issue is Discord audio capture (sample rate, opus decoding)
    └─> No:  Continue...

audio_48000hz.wav sounds wrong?
    └─> Yes: Issue is in VAD slicing / utterance extraction
    └─> No:  Continue...

audio_16khz.wav sounds wrong?
    └─> Yes: Issue is in resampling (audio_utils.resample_wav)
    └─> No:  Audio is fine, issue is Whisper interpretation

Whisper returning garbage (ॐ, emojis, repeated chars)?
    └─> Likely hallucination on noise/silence that VAD thought was speech
    └─> Try: raise VAD threshold, add language hint, filter short utterances
```

**Check audio metadata:**

```bash
# Verify WAV format and duration
file voice_debug/session_*/users/*/utterances/0/audio_*.wav

# Get exact duration (requires ffprobe)
ffprobe -v quiet -show_entries format=duration -of csv=p=0 \
  voice_debug/session_*/users/*/utterances/0/audio_48000hz.wav
```

## Common Issues

### Low VAD Coverage

**Symptom:** Analyzer shows < 10% VAD coverage, transcripts are sparse.

**Causes:**
- VAD threshold too high (missing quiet speech)
- Audio level too low from Discord
- Background noise confusing the detector

**Debug:**
1. Play `raw_buffer.wav` - can you hear speech?
2. Check `vad_segments.json` - are segments being detected?
3. Try EnergyVAD with lower threshold for comparison

### Empty Transcriptions

**Symptom:** Audio file has speech but `stt_result.json` shows empty text.

**Causes:**
- Audio too short (< 500ms filtered by default)
- Sample rate mismatch (fixed in recent versions)
- Audio corruption

**Debug:**
1. Check `audio_16khz.wav` - is it playable?
2. Check utterance duration in manifest
3. Try uploading the WAV to OpenAI playground manually

### High STT Latency

**Symptom:** `stt_latency_ms` consistently > 3000ms.

**Causes:**
- Large audio chunks
- Network issues to OpenAI
- Rate limiting

**Debug:**
1. Check chunk durations - are they too long?
2. Review `chunk_seconds` setting (default 10s)

## Docker Debugging

Both docker-compose files support debug environment variables:

```yaml
# docker/docker-compose.prod.yml
environment:
  - LOG_LEVEL=${LOG_LEVEL:-INFO}
  - VOICE_DEBUG=${VOICE_DEBUG:-}
  - VOICE_DEBUG_DIR=/app/voice_debug

volumes:
  - ./voice_debug:/app/voice_debug
```

### Enable debugging for production:

```bash
# Create .env or export variables
export LOG_LEVEL=DEBUG
export VOICE_DEBUG=1

# Start with debug enabled
docker-compose -f docker/docker-compose.prod.yml up -d

# Watch logs
docker-compose -f docker/docker-compose.prod.yml logs -f

# After testing, captured files are in ./voice_debug/
python scripts/analyze_voice_session.py ./voice_debug/session_*/
```

### Dev environment:

The dev compose mounts the entire project, so voice_debug appears automatically:

```bash
# In docker/.env or export
LOG_LEVEL=DEBUG
VOICE_DEBUG=1

# Start dev environment
make dev-env

# Inside container
python -m clanker_bot

# Exit and analyze on host
python scripts/analyze_voice_session.py voice_debug/session_*/
```

## Pipeline Test Script

For testing the pipeline offline (without Discord), use `scripts/test_audio_pipeline.py`. This runs the full VAD → STT pipeline against real audio with known transcripts, measuring accuracy.

### Setup

```bash
# Download LibriSpeech and AMI test samples (~50MB)
make download-test-audio

# Or manually
python scripts/download_test_audio.py --all
```

### VAD Testing (no API key needed)

```bash
python scripts/test_audio_pipeline.py
```

This compares **Silero VAD** vs **Energy VAD** on real speech:
- Reports segments detected per sample
- Shows speech coverage percentage
- Identifies potential threshold issues

Example output:
```
📁 1089-134686-0000
   Duration: 5230ms (5.2s)
   Ground truth: "he hoped there would be stew for dinner..."

   🤖 Silero VAD:
      Segments: 3
      Speech detected: 4850ms (92.7%)

   ⚡ Energy VAD:
      Segments: 5
      Speech detected: 4200ms (80.3%)
```

### Full STT Testing with WER

```bash
OPENAI_API_KEY=sk-... python scripts/test_audio_pipeline.py --stt
```

This measures **Word Error Rate (WER)** against ground truth transcripts:

```
📁 1089-134686-0000
   Ground truth: "he hoped there would be stew for dinner"
   Transcribed:  "he hoped there would be stew for dinner"

   📈 Metrics:
      Events: 1
      WER: 0.00%
      Edit distance: 0 / 8 words

SUMMARY
  Samples tested: 3
  Average WER: 2.5%
  Best WER: 0.00%
  Worst WER: 5.00%

  ✅ GOOD - WER under 10%
```

### Test Data Sources

| Dataset | Purpose | Ground Truth |
|---------|---------|--------------|
| **LibriSpeech** | Clean single-speaker speech | Yes - exact transcripts |
| **AMI Corpus** | Multi-speaker meeting audio | Partial - speaker segments |

See `tests/data/README.md` for detailed test data documentation.

### Using Test Script for Debugging

If live transcription quality is poor:

1. **Run VAD-only test** to verify speech detection works:
   ```bash
   python scripts/test_audio_pipeline.py --librispeech
   ```

2. **Run full STT test** to get baseline WER:
   ```bash
   OPENAI_API_KEY=sk-... python scripts/test_audio_pipeline.py --stt
   ```

3. **Compare results:**
   - If test WER is good but live is bad → likely Discord audio issue
   - If test WER is also bad → check Whisper API or model settings
   - If VAD coverage is low → tune thresholds or check audio levels

## Sample Rate Handling

Discord audio arrives at **48kHz**. Whisper is optimized for **16kHz**.

The pipeline automatically resamples:
1. Audio captured at 48kHz from Discord
2. VAD processes at native rate (Silero resamples internally)
3. Before STT, audio is resampled to 16kHz
4. Debug capture saves both versions for comparison

If transcription quality is poor, compare `audio_48000hz.wav` vs `audio_16khz.wav` to verify resampling is working correctly.
