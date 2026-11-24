# Roadmap

Build queue for agents. What needs Steve specifically lives in `HUMAN_TODO.md`.

## Editor

- [ ] **Fix time division when splitting turns.** Today `Split` divides the
  *text* at the caret but the *time* at the playhead, or at the segment's
  midpoint when the playhead isn't inside the segment
  (`onSplit` in `src/stt/webapp/static/app.js`, same logic in
  `src/stt/review/static/app.js`). So a caret split with the audio elsewhere
  gives both halves wrong timestamps and misassigns the word timings. Derive
  the split time from the word timings instead: count the words before the
  caret and use that word's `start` (fall back to the playhead only if the
  segment has no word timings). Both editors.

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
- [ ] **Voiceprint ID (parked).** Enrol Steve's voice, embed each diarized
  segment (pyannote), cluster against the AssemblyAI labels, and label Steve
  across every file. Judged not worth it on 2026-11-08: about a day of work, a
  local model over hundreds of hours, and it only ever reliably identifies
  Steve. Revisit if the chronicle project needs "who is Steve" at scale.
- [ ] **File metadata is a dead end.** Checked 2026-11-08: the voice memos
  carry only an Apple `voice-memo-uuid` tag. Nothing identifies participants
  beyond the title and date. Recorded here so nobody re-checks.
