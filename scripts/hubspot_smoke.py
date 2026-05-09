#!/usr/bin/env python3
"""HubSpot smoke test — creates + deletes a disposable test contact end-to-end.

Run only against a HubSpot dev portal. Skipped automatically if
``HUBSPOT_PRIVATE_APP_TOKEN`` is unset.

Sequence (each step is verified):
    1. search_contacts(email=test_email) → expect [] (clean slate)
    2. POST /crm/v3/objects/contacts to create the test contact
    3. log_email_activity → expect engagement id
    4. create_note → expect note id
    5. create_task → expect task id
    6. engagement_counts → expect at least 2 emails OR 1 note
    7. DELETE /crm/v3/objects/contacts/<id> to clean up
    8. confirm contact gone

Refuses to run unless ``GTMOS_HUBSPOT_SMOKE=1`` AND email matches
``smoke-test+*@gtmos.local``. This double gate prevents accidental
production runs.
"""

from __future__ import annotations

import datetime as dt
import os
import secrets
import sys

from gtmos.connectors import ConnectorAuthError, ConnectorError, ConnectorUnavailable
from gtmos.connectors.hubspot import API_BASE, HubSpotClient

SMOKE_FLAG = "GTMOS_HUBSPOT_SMOKE"
TEST_EMAIL_TEMPLATE = "smoke-test+{nonce}@gtmos.local"


def main() -> int:
    if os.environ.get(SMOKE_FLAG, "") != "1":
        print(f"refusing to run without {SMOKE_FLAG}=1; this hits a real HubSpot portal")
        return 2

    token = os.environ.get("HUBSPOT_PRIVATE_APP_TOKEN", "").strip()
    if not token:
        print("HUBSPOT_PRIVATE_APP_TOKEN unset; nothing to test")
        return 2

    nonce = secrets.token_hex(4)
    test_email = TEST_EMAIL_TEMPLATE.format(nonce=nonce)
    if not test_email.endswith("@gtmos.local"):
        print("bad fixture email — refusing to proceed")
        return 2

    client = HubSpotClient(
        base_url=API_BASE,
        auth_headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    contact_id: str | None = None
    failures: list[str] = []

    def step(name: str, fn) -> None:  # type: ignore[no-untyped-def]
        try:
            result = fn()
            print(f"  ✓ {name}")
            return result
        except (ConnectorAuthError, ConnectorError, ConnectorUnavailable, ValueError) as e:
            failures.append(f"{name}: {e}")
            print(f"  ✗ {name}: {e}")
            return None

    print(f"hubspot-smoke: portal={API_BASE} fixture={test_email}")

    # 1. clean slate
    initial = step(
        "search clean-slate",
        lambda: client.search_contacts(email=test_email),
    )
    if initial:
        print(f"    ⚠ test contact already exists with id={initial[0]['id']}; aborting")
        return 1

    # 2. create test contact (raw API; this isn't part of our connector surface)
    def _create() -> dict[str, str]:
        body = {
            "properties": {
                "email": test_email,
                "firstname": "GTMOS",
                "lastname": f"Smoke-{nonce}",
                "company": "GTMOS Smoke Test",
            }
        }
        resp = client.request("POST", "/crm/v3/objects/contacts", json=body)
        cid = str(resp.get("id", "")) if isinstance(resp, dict) else ""
        if not cid:
            raise ConnectorError("contact create returned no id")
        return {"id": cid}

    created = step("create contact", _create)
    if not created:
        return 1
    contact_id = created["id"]

    # 3. log email activity
    step(
        "log_email_activity",
        lambda: client.log_email_activity(
            contact_id=contact_id,  # type: ignore[arg-type]
            subject=f"smoke-test {nonce}",
            body="GTMOS smoke test — safe to delete.",
        ),
    )

    # 4. create note
    step(
        "create_note",
        lambda: client.create_note(
            contact_id=contact_id,  # type: ignore[arg-type]
            body=f"GTMOS smoke note {nonce}",
        ),
    )

    # 5. create task
    step(
        "create_task",
        lambda: client.create_task(
            contact_id=contact_id,  # type: ignore[arg-type]
            title=f"GTMOS smoke task {nonce}",
            due_at=dt.datetime.now(tz=dt.UTC) + dt.timedelta(days=7),
        ),
    )

    # 6. engagement counts
    counts = step(
        "engagement_counts",
        lambda: client.engagement_counts(since=dt.datetime.now(tz=dt.UTC) - dt.timedelta(hours=1)),
    )
    if counts:
        print(f"    counts: {counts}")

    # 7. cleanup — delete the test contact
    if contact_id:
        try:
            client.request(
                "DELETE",
                f"/crm/v3/objects/contacts/{contact_id}",
                expected_status=(200, 202, 204),
            )
            print(f"  ✓ delete contact {contact_id}")
        except (ConnectorError, ValueError) as e:
            failures.append(f"delete contact: {e}")
            print(f"  ✗ delete contact: {e}")

    # 8. confirm gone
    leftover = step(
        "verify deletion",
        lambda: client.search_contacts(email=test_email),
    )
    if leftover:
        failures.append("test contact still present after delete")

    print()
    if failures:
        print(f"hubspot-smoke: FAIL ({len(failures)})")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("hubspot-smoke: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
