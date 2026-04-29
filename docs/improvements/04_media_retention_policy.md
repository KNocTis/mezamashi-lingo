# Media Retention Policy

**Rank:** Lowest

Your new `logger.py` keeps logs for 30 days, which is great. However, `downloads/` containing `.mp4` and `.wav` (vocal) files will consume massive amounts of disk space rapidly. We suggest setting up a cron job or adding a Python hook to automatically purge `.mp4` and `.wav` files older than 7 days, while retaining the lightweight `.html`, `.json`, and `.srt` text files indefinitely for your review.
