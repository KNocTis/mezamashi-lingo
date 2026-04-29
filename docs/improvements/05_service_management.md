# Service Management for Other OS

**Rank:** Lowest

The script is meant for daily execution. We've implemented `launchd` for macOS, but we can save the implementation for other operating systems (like `systemd` for Linux or Task Scheduler for Windows) for the future. This ensures that it runs automatically in the background at a specific time (e.g., 6:00 AM) so that the vocabulary list is ready when you wake up.
