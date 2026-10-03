# Transcription quality — test video "How MrBeast Solved YouTube" (14:10)

Reference: YouTube's own captions, pasted by the owner on 2026-10-03 and stored outside git (`../epoch-data/validation/mrbeast_youtube_captions.txt`, third-party text).

**YouTube's captions are machine-made too** (they contain "Baird across", "Mr abuse", "miservous", "doll moments"). So:
- The headline number is **disagreement**, not word error rate against the truth.
- Each disagreement was then judged by hand from sentence context. Nobody listened to the audio, so treat the judgements as informed, not certain.

Tool: `scripts/asr_eval.py` (normalises case, punctuation, number words, "Mr Beast"/"MrBeast"; Levenshtein alignment; per-minute breakdown; list of disagreement spans).

## Run 1: shipped settings (`condition_on_previous_text=True`)

| Measure | Value |
|---|---|
| Reference words | 2813 |
| Our words | 2786 |
| Disagreement vs YouTube | **5.6%** (78 substitutions, 53 missing in ours, 26 extra in ours) |
| Worst minutes | 12:00–13:00 **23%** (the played MrBeast clip with music and applause), 1:00–2:00 14% (number formatting, a quoted clip), 13:00–14:00 8% |
| Every other minute | 2–6% |

### Who was right, by hand (≈75 disagreement spans)

| Judgement | Approx. count | Examples (ours vs YouTube) |
|---|---|---|
| **Ours right, YouTube wrong** | ~25 | buried / "Baird"; retention / "attention" (twice); "Bro, I roast" / "before I rush"; MrBeast applies / "Mr P supplies"; MrBeast / "Mr abuse" (twice); MrBeast's / "miservous"; grip / "drip"; contractually obligated / "obvious"; ends with an ad read / "items Mr B's eyes when Audrey"; dull / "doll"; friends roast his / "fans of roses"; 12 second mark / "12th second one" |
| **YouTube right, ours wrong** | ~12 | **"$50" for "twenty dollars"** (changes the example's meaning); tracked / "trapped"; who / "not only"; "how long" / "all along"; "bodyless" / "body of his"; "Mr. Abuse" at 13:38 (YouTube's "Mr peace" is wrong too) |
| **Words lost in ours** | 3 spots | 5:57 "closely studying as many MrBeast" and 13:40 "will go back": Whisper **looped** there, the loop guard (A-01) removed the junk, and the real words under it are gone. 12:38: about 10 words of the music/applause clip ("literally said…what is wrong with you") |
| **Equivalent** (formatting, contractions, gonna/going to, $500,000 vs five hundred thousand) | ~20 | not real errors |
| **Unclear without listening** | ~15 | "operation fool" / "bull"; "to make this a little better" (only in ours); "there are massive" / "with a mass of" |

**Estimate:** on clean English narration, large-v3 is **better than YouTube's captions** for names and jargon, with roughly 2–3% true word errors. Its errors cluster in three places:
1. **Played clips with music** (12:00–13:00).
2. **Repetition loops**, which leave holes after the guard removes them.
3. **A few meaning-changing numbers** ($50 vs $20).

**Formatting defect (separate from word accuracy):** 426 s (7:43–14:10) came back without punctuation or casing. This breaks sentence-level analysis.

## Run 2: `condition_on_previous_text=False` (A-03), full video re-transcribed 2026-10-03

| Measure | Run 1 (shipped) | Run 2 (A-03) |
|---|---|---|
| Disagreement vs YouTube | 5.6% | **4.9%** |
| Words missing in ours | 53 | **39** |
| Repetition loops removed by the guard | 3 (holes at 5:57, 9:52, 13:40) | **0** |
| Words aligned | 2790/2790 | 2818/2818 |
| Unpunctuated transcript | 426 s (one block, 7:43–14:10) | **190 s** in short runs |
| ASR time (CPU, 6 threads) | ≈41 min | ≈39 min |

The lost words are back: "…closely studying as many MrBeast…and tweets" (5:57) and "will go back and cut out every dull moment… 10 friends roast his videos" (13:40).

The remaining unpunctuated runs are short and mostly sit inside played clips: the MrBeast interview around 3:50, the Antarctica clip at 7:42, and the ending clip at 12:38. The 12:00–13:00 minute is still the worst (19% disagreement, music and applause). A-03 is kept.

## Chapters vs the creator's own chapters (bonus check)
The creator's chapter marks: Intro 0:00 · First 5 Seconds 0:25 · First 20 Seconds 2:26 · Video Body 7:15 · Video End 11:58 · Post-Production 13:38.

Our LLM chapters are finer (20 of them). **Each of the creator's 5 boundaries has one of ours within 15 s:**

| Creator boundary | Ours | Difference |
|---|---|---|
| 0:25 | 0:29 | +4 s |
| 2:26 | 2:32 | +6 s |
| 7:15 | 7:19 | +4 s |
| 11:58 | 12:13 | +15 s |
| 13:38 | 13:29 | −9 s |

## What this does not show
- Hindi or Hinglish accuracy: never tested.
- Accuracy on noisy or music-heavy videos beyond the one clip here.
- Anything about retention.
