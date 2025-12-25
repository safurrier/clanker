"""Metrics for evaluating transcription accuracy.

This module provides Word Error Rate (WER) calculation and related metrics
for comparing transcription output against ground truth references.
"""

from __future__ import annotations

import re


def normalize_text(text: str) -> str:
    """Normalize text for WER calculation.

    - Lowercase
    - Remove punctuation
    - Collapse whitespace
    - Strip leading/trailing whitespace

    Args:
        text: Raw text to normalize

    Returns:
        Normalized text suitable for WER comparison
    """
    # Lowercase
    text = text.lower()

    # Remove punctuation (keep only alphanumeric and spaces)
    text = re.sub(r"[^\w\s]", "", text)

    # Collapse multiple spaces to single space
    text = re.sub(r"\s+", " ", text)

    # Strip
    return text.strip()


def levenshtein_distance(ref: list[str], hyp: list[str]) -> tuple[int, int, int, int]:
    """Calculate Levenshtein distance between two word sequences.

    Returns edit distance and counts of substitutions, insertions, and deletions.

    Args:
        ref: Reference (ground truth) word list
        hyp: Hypothesis (predicted) word list

    Returns:
        Tuple of (distance, substitutions, insertions, deletions)
    """
    m, n = len(ref), len(hyp)

    # dp[i][j] = (distance, subs, ins, dels) to transform ref[:i] to hyp[:j]
    dp = [[(0, 0, 0, 0) for _ in range(n + 1)] for _ in range(m + 1)]

    # Base cases
    for i in range(1, m + 1):
        dp[i][0] = (i, 0, 0, i)  # Delete all ref words

    for j in range(1, n + 1):
        dp[0][j] = (j, 0, j, 0)  # Insert all hyp words

    # Fill DP table
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if ref[i - 1] == hyp[j - 1]:
                # Match - no operation needed
                dp[i][j] = dp[i - 1][j - 1]
            else:
                # Consider substitution, insertion, deletion
                sub = dp[i - 1][j - 1]
                ins = dp[i][j - 1]
                delete = dp[i - 1][j]

                # Choose minimum distance operation
                min_dist = min(sub[0] + 1, ins[0] + 1, delete[0] + 1)

                if sub[0] + 1 == min_dist:
                    dp[i][j] = (min_dist, sub[1] + 1, sub[2], sub[3])
                elif ins[0] + 1 == min_dist:
                    dp[i][j] = (min_dist, ins[1], ins[2] + 1, ins[3])
                else:
                    dp[i][j] = (min_dist, delete[1], delete[2], delete[3] + 1)

    return dp[m][n]


def calculate_wer(reference: str, hypothesis: str) -> float:
    """Calculate Word Error Rate (WER) between reference and hypothesis.

    WER = (Substitutions + Insertions + Deletions) / Reference Words

    Lower is better. 0.0 = perfect match, 1.0 = completely wrong.

    Args:
        reference: Ground truth transcription
        hypothesis: Predicted transcription

    Returns:
        WER as a float between 0.0 and potentially > 1.0
        (can exceed 1.0 if hypothesis is much longer than reference)

    Examples:
        >>> calculate_wer("hello world", "hello world")
        0.0
        >>> calculate_wer("hello world", "hello")
        0.5
        >>> calculate_wer("the cat sat", "the dog sat")
        0.333...
    """
    # Normalize both texts
    ref_normalized = normalize_text(reference)
    hyp_normalized = normalize_text(hypothesis)

    # Split into words
    ref_words = ref_normalized.split()
    hyp_words = hyp_normalized.split()

    # Handle edge cases
    if not ref_words:
        return 0.0 if not hyp_words else float(len(hyp_words))

    if not hyp_words:
        return 1.0  # All reference words are deletions

    # Calculate Levenshtein distance
    distance, _, _, _ = levenshtein_distance(ref_words, hyp_words)

    return distance / len(ref_words)


def calculate_wer_details(
    reference: str, hypothesis: str
) -> dict[str, float | int | list[str]]:
    """Calculate WER with detailed breakdown.

    Args:
        reference: Ground truth transcription
        hypothesis: Predicted transcription

    Returns:
        Dictionary with:
        - wer: Word Error Rate
        - substitutions: Number of substitution errors
        - insertions: Number of insertion errors
        - deletions: Number of deletion errors
        - reference_words: Number of words in reference
        - hypothesis_words: Number of words in hypothesis
        - reference_text: Normalized reference
        - hypothesis_text: Normalized hypothesis
    """
    ref_normalized = normalize_text(reference)
    hyp_normalized = normalize_text(hypothesis)

    ref_words = ref_normalized.split()
    hyp_words = hyp_normalized.split()

    if not ref_words:
        return {
            "wer": 0.0 if not hyp_words else float(len(hyp_words)),
            "substitutions": 0,
            "insertions": len(hyp_words),
            "deletions": 0,
            "reference_words": 0,
            "hypothesis_words": len(hyp_words),
            "reference_text": ref_normalized,
            "hypothesis_text": hyp_normalized,
        }

    distance, subs, ins, dels = levenshtein_distance(ref_words, hyp_words)

    return {
        "wer": distance / len(ref_words),
        "substitutions": subs,
        "insertions": ins,
        "deletions": dels,
        "reference_words": len(ref_words),
        "hypothesis_words": len(hyp_words),
        "reference_text": ref_normalized,
        "hypothesis_text": hyp_normalized,
    }


def calculate_cer(reference: str, hypothesis: str) -> float:
    """Calculate Character Error Rate (CER).

    Similar to WER but operates on characters instead of words.
    Useful for evaluating proper noun handling and spelling accuracy.

    Args:
        reference: Ground truth transcription
        hypothesis: Predicted transcription

    Returns:
        CER as a float between 0.0 and potentially > 1.0
    """
    ref_normalized = normalize_text(reference)
    hyp_normalized = normalize_text(hypothesis)

    # Treat each character as a "word" for Levenshtein
    ref_chars = list(ref_normalized.replace(" ", ""))
    hyp_chars = list(hyp_normalized.replace(" ", ""))

    if not ref_chars:
        return 0.0 if not hyp_chars else float(len(hyp_chars))

    distance, _, _, _ = levenshtein_distance(ref_chars, hyp_chars)

    return distance / len(ref_chars)
