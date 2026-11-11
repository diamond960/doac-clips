# doac-clips

Clip queue for The Diary Of A CEO clips, run by Claude's daily scheduled task.

- `moments.json` - picked 2-3 minute moments (exact start/end, hook, titles, hashtags) and whether each has been posted.
- `requests/transcript/<video_id>` - pushing this file makes the **transcript** workflow save that episode's captions to `transcripts/`, so new moments can be picked.
- Clips are cut by OpusClip or vidIQ and posted through Metricool to TikTok @clip.s74 and the clips YouTube channel at 1pm, 4pm and 8pm New York time.
