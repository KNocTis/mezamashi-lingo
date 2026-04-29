# Concurrent Processing

**Rank:** Secondary

During the download, transcribe, and translate phases, processing multiple selected videos sequentially takes time. Implementing `asyncio` or `concurrent.futures` to process non-interdependent videos in parallel could significantly speed up the daily run.
