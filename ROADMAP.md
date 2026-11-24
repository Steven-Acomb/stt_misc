# Roadmap

Build queue for agents. What needs Steve specifically lives in `HUMAN_TODO.md`.

## Editor

- [ ] **Fix time division when splitting turns.** Today `Split` sets the
  boundary time from the playhead, or the segment midpoint when the playhead
  isn't inside the segment (`onSplit` in `src/stt/webapp/static/app.js`, same
  in `src/stt/review/static/app.js`). Neither carries the intended moment:
  Steve does not pause the audio or park the playhead at the boundary when he
  splits, so there is no app state that holds the right time, and the result
  is wrong timestamps on both halves. Steve's fix, two parts that only work
  together:
  1. **A way to set a turn's boundary time by hand in the app.** There is
     none today, which is an oversight regardless of the split bug. Must not
     require scrubbing hours of audio to find the moment.
  2. **Default the split time proportionally**: the boundary lands between the
     segment's existing start and end in proportion to how far into the text
     the split falls.
  Alternative default, Claude's suggestion (2026-11-24): the segment already
  has per-word timestamps, so map the text split point to the Nth word and use
  that word's `start`. Same idea as (2) but proportional in words, and exact
  where the text is unedited; fall back to the linear proportion when the
  edited text no longer lines up with the word list or a segment has no word
  timings. (1) is needed either way.

## Speaker attribution (from the 2026-11-08 backlog discussion)

Context: the Sphere week-by-week transcripts are produced with no review, so
every speaker is "Speaker N". Steve is in every recording; one-on-ones name the
other person in the file title; ambient "Workday" recordings have an unknown
cast. Options discussed, roughly in order of value per effort:

- [ ] **LLM speaker-naming pass for one-on-ones.** One Claude call per
  transcript reads the first few minutes plus the file title ("Convo w. Mitch",
  "Loic 1_1") and decides which letter is Steve and which is the named person,
  then writes the names into the JSON `speaker_names`. No review needed.
  Scope: only titles that read like a one-on-one (the same `_TWO_PARTY` rule
  `stt ingest` uses for the 2-speaker hint). Leave ambient recordings numbered.
- [ ] **Cap auto-detected speakers on ambient recordings.** AssemblyAI returned
  up to 16 "speakers" on trade-show and long office recordings (e.g. "IMS WSC
  rec 5": 15, "Sphere Workday 03-24-25 9": 16). A ceiling of ~6 on auto-detect
  would stop the over-splitting. Only for future runs; changes output, so
  Steve decides the number.
- [ ] **Split long single-speaker turns on conversational cues.** When
  diarization collapses (two similar voices, e.g. the twin coffee: one
  21-minute "turn"), the words are right but one label spans both people. An
  LLM pass that splits on question/answer and address cues could recover
  turns approximately. Speculative; mark results as unreviewed.
- [ ] **Voiceprint ID (Steve wants to try it; not scheduled).** Two stages:
  1. Enrol Steve's voice; for every transcript, embed a few seconds of each
     AssemblyAI speaker cluster (pyannote speaker embeddings; no re-diarizing),
     compare, and name the matching label "Steve" in `speaker_names`.
  2. Bootstrap the rest: in a one-on-one, the non-Steve voice is the person in
     the title ("Convo w. Mitch" → Mitch), so each labelled one-on-one becomes
     an enrolment sample. The library (Mitch, Loic, Alex Hu, Stelios, …) then
     labels the ambient Workday recordings too.
  Sized 2026-11-08 at about a day of glue. Compute is not a concern: the
  desktop has an RTX 4070 SUPER (12 GB); PyTorch is not in the venv yet.
  Parked that day only because the week-by-week transcripts were needed ASAP.
- [ ] **File metadata is a dead end.** Checked 2026-11-08: the voice memos
  carry only an Apple `voice-memo-uuid` tag. Nothing identifies participants
  beyond the title and date. Recorded here so nobody re-checks.
