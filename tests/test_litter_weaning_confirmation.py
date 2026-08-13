import os
from datetime import datetime, timedelta

from modules.pig_weights import pig_weights_service


def setup_module():
    os.environ["OWNER_SESSION_SECRET"] = "test-only-weaning-confirmation-secret-32"


def test_weaning_confirmation_is_actor_digest_and_expiry_bound():
    now = datetime(2026, 8, 13, 10, 0, 0)
    binding = pig_weights_service._weaning_confirmation_binding("digest-a", "owner-a", now=now)
    assert pig_weights_service._valid_weaning_confirmation(binding, "digest-a", "owner-a", now=now)
    assert not pig_weights_service._valid_weaning_confirmation(binding, "digest-b", "owner-a", now=now)
    assert not pig_weights_service._valid_weaning_confirmation(binding, "digest-a", "owner-b", now=now)
    assert not pig_weights_service._valid_weaning_confirmation(
        binding, "digest-a", "owner-a", now=now + timedelta(minutes=31)
    )
    altered = dict(binding, signature="0" * 64)
    assert not pig_weights_service._valid_weaning_confirmation(altered, "digest-a", "owner-a", now=now)
