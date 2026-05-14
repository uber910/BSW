from __future__ import annotations

import uvicorn

from line_provider.settings.config import LineProviderSettings


def main() -> None:
    settings = LineProviderSettings()
    uvicorn.run(
        "line_provider.app:build_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        log_config=None,
    )


if __name__ == "__main__":
    main()
