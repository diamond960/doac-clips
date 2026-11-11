# doac-clips

Free clipper for The Diary Of A CEO, run by GitHub Actions and driven by Claude.

1. Claude adds `requests/transcript/<video_id>` → **transcript** workflow saves the captions to `transcripts/`.
2. Claude reads the transcript, picks the best moments (each clip 2–3 minutes: 120–175 s, never over 178 s so YouTube still treats it as a Short) and adds `jobs/<video_id>.json`.
3. **cut** workflow downloads the episode, makes vertical 1080×1920 clips with captions, and publishes them under the release `clips-<video_id>`. Links land in `output/<video_id>.json`.
4. Claude schedules the clips to TikTok and YouTube Shorts through Metricool.

Errors are written to `transcripts/<id>.error.txt` or `output/<id>.error.txt`.
