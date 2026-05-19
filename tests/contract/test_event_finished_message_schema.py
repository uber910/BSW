"""Contract test: EventFinishedMessage must be byte-for-byte identical
across line_provider and bet_maker.

A failing test here means a developer modified one copy without
updating the other — CI breaks the PR before deployment drift can
occur in production.
"""

from __future__ import annotations

import json

from bet_maker.schemas.messages import EventFinishedMessage as BMMessage
from line_provider.schemas.messages import EventFinishedMessage as LPMessage


def test_schemas_are_identical() -> None:
    lp_schema = json.dumps(LPMessage.model_json_schema(), sort_keys=True)
    bm_schema = json.dumps(BMMessage.model_json_schema(), sort_keys=True)
    assert lp_schema == bm_schema, (
        "EventFinishedMessage schema drift detected between line_provider "
        "and bet_maker — re-sync src/bet_maker/schemas/messages.py with "
        "src/line_provider/schemas/messages.py byte-for-byte."
    )


def test_schema_version_field_is_present_with_default_one() -> None:
    lp_fields = LPMessage.model_fields
    bm_fields = BMMessage.model_fields
    assert "schema_version" in lp_fields
    assert "schema_version" in bm_fields
    assert lp_fields["schema_version"].default == 1
    assert bm_fields["schema_version"].default == 1


def test_extra_forbid_is_set_on_both() -> None:
    assert LPMessage.model_config.get("extra") == "forbid"
    assert BMMessage.model_config.get("extra") == "forbid"
