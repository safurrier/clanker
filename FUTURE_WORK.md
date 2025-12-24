# Future Work

Ideas and improvements for future development.

## Real Audio E2E Testing

### Overview

Add end-to-end tests using actual speech datasets with ground-truth transcripts to validate the full audio capture and transcription pipeline.

### Recommended Datasets

#### LibriSpeech (Quick Testing)
- **Download**: http://www.openslr.org/12
- **Subset**: `test-clean.tar.gz` (346MB)
- **Contains**: ~5 hours of clean English speech, 16kHz
- **Use case**: Fast validation tests with known transcripts

**Setup**:
```bash
# Download and extract samples
cd tests/data
wget http://www.openslr.org/resources/12/test-clean.tar.gz
tar -xzf test-clean.tar.gz

# Select 3 short samples (<10 seconds each)
# LibriSpeech structure: LibriSpeech/test-clean/<speaker>/<chapter>/*.flac
# Example: LibriSpeech/test-clean/1089/134686/1089-134686-0000.flac

# Transcripts are in .trans.txt files (one line per audio file)
```

#### AMI Corpus (Multi-Speaker Meetings)
- **Download**: https://groups.inf.ed.ac.uk/ami/download/
- **Contains**: 100 hours of 4-person meeting recordings
- **Use case**: Realistic multi-speaker conversation testing

**Setup**:
```bash
# Download individual meeting samples
# AMI provides separate audio channels per speaker
# Extract 1-2 minute segments for testing
```

### Planned Test Cases

#### 1. LibriSpeech Validation Test
```python
@pytest.mark.network()
@pytest.mark.slow()
async def test_librispeech_accuracy():
    """Validate transcription accuracy with LibriSpeech samples."""
    # Load audio and ground truth transcript
    audio_path = test_data_dir / "librispeech/1089-134686-0000.flac"
    ground_truth = load_librispeech_transcript(audio_path)
    
    # Run through full pipeline
    detector = SileroVAD(warmup=True)
    stt = OpenAISTT()  # Requires OPENAI_API_KEY
    
    events = await process_audio(audio_path, detector, stt)
    predicted = " ".join(e.text for e in events)
    
    # Calculate Word Error Rate (WER)
    wer = calculate_wer(ground_truth, predicted)
    assert wer < 0.05, f"WER too high: {wer:.2%} (expected <5%)"
```

#### 2. Multi-Speaker AMI Corpus Test
```python
@pytest.mark.network()
@pytest.mark.slow()
async def test_ami_multispeaker():
    """Test multi-speaker conversation from AMI Corpus."""
    # Load 4-speaker meeting segment
    speakers = {
        1: load_ami_channel("ES2002a.Mix-Headset-00.wav"),
        2: load_ami_channel("ES2002a.Mix-Headset-01.wav"),
        3: load_ami_channel("ES2002a.Mix-Headset-02.wav"),
        4: load_ami_channel("ES2002a.Mix-Headset-03.wav"),
    }
    
    # Process all speakers through pipeline
    events = await process_multispeaker(speakers)
    
    # Verify chronological ordering
    assert_chronological_order(events)
    
    # Verify all speakers detected
    assert {e.speaker_id for e in events} == {1, 2, 3, 4}
```

#### 3. Timestamp Accuracy Test
```python
@pytest.mark.network()
async def test_timestamp_accuracy():
    """Verify VAD timestamps match actual speech positions."""
    # Use LibriSpeech sample with known utterance boundaries
    audio, timestamps = load_sample_with_annotations()
    
    # Run VAD detection
    detector = SileroVAD(warmup=True)
    segments = detector.detect(audio, 16000)
    
    # Compare detected timestamps with annotations
    for detected, expected in zip(segments, timestamps):
        # Allow 100ms tolerance
        assert abs(detected.start_ms - expected.start_ms) < 100
        assert abs(detected.end_ms - expected.end_ms) < 100
```

### Implementation Steps

1. **Download samples** (one-time setup):
   ```bash
   make download-test-audio  # Create this target
   ```

2. **Create test data fixtures** in `tests/conftest.py`:
   ```python
   @pytest.fixture(scope="session")
   def librispeech_samples():
       """Load LibriSpeech test samples with transcripts."""
       # Parse .trans.txt files
       # Return list of (audio_path, transcript) tuples
   ```

3. **Add WER calculation** in `tests/metrics.py`:
   ```python
   def calculate_wer(reference: str, hypothesis: str) -> float:
       """Calculate Word Error Rate using edit distance."""
   ```

4. **Create test suite** in `tests/test_real_audio.py`

### Storage Considerations

- Store samples in `tests/data/librispeech/` and `tests/data/ami/`
- Add to `.gitignore` (files are large)
- Document download process in `tests/data/README.md`
- Consider caching samples in CI/CD for faster test runs

### Dependencies

- `pytest-asyncio` - Already included
- OpenAI API key for Whisper STT
- `python-Levenshtein` (optional) - For fast WER calculation

### Metrics to Track

- **Word Error Rate (WER)**: <5% for clean speech
- **Utterance Detection Rate**: >95% of utterances detected
- **Timestamp Accuracy**: ±100ms tolerance
- **Multi-speaker Ordering**: 100% chronological

### Related Work

- Existing synthetic tests: `tests/test_audio_scenarios.py`
- VAD regression test: `test_silero_vad_timestamps_match_window_size`
- Documentation: `docs/audio-capture.md`, `docs/transcript-examples.md`
