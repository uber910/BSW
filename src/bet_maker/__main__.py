from __future__ import annotations

import uvicorn

from bet_maker.settings.config import BetMakerSettings


def main() -> None:
    settings = BetMakerSettings()
    uvicorn.run(
        "bet_maker.app:build_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        log_config=None,
    )


if __name__ == "__main__":
    main()
