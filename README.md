# CutCapture Cloud

A small single-owner prototype: YouTube link → server download → MP4 download and browser-local cut capture.

Docker deployment on Render. Choose **Free**, one instance, Singapore. Set `APP_PASSWORD` and `SECRET_KEY` to strong independent random values through Render environment settings. No credentials belong in source control.

Limits: 720p H.264 MP4, 15 minutes, 180 MB per finished video, one active download, three retained jobs, 30 seconds between starts. Outputs are temporary and lost on restarts. Completed jobs expire after one hour; use the delete button to remove sooner. One Gunicorn worker is required because this prototype stores job state in memory.

The free hosting platform can sleep or restart. YouTube can reject downloads from datacenter IPs. Successful deployment does not prove a particular YouTube clip downloads. No cookies, proxy rotation, login bypass, or authentication challenge bypass is provided. Use media you are permitted to download.

Browser cut detection samples every 0.1–0.2 seconds and is approximate. Rapid cuts, dissolves and flashes can produce omissions or false positives. Extraction and exports happen in the user's browser. Uploaded local files never leave the browser. YouTube URL downloads run on the server and are password protected.

Run tests with `python -m unittest test_server.py`. These tests validate HTTP access controls and worker outcome handling using synthetic jobs, not live YouTube connectivity.
