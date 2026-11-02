import pytest
from pydantic import ValidationError

from app.schemas.alert_channel import AlertChannelCreate


def test_valid_email_is_accepted():
    channel = AlertChannelCreate(
        type="email",
        destination="sumit@example.com",
    )

    assert channel.type == "email"
    assert channel.destination == "sumit@example.com"


def test_default_channel_type_is_email():
    channel = AlertChannelCreate(
        destination="sumit@example.com",
    )

    assert channel.type == "email"


def test_email_is_normalized():
    channel = AlertChannelCreate(
        type=" EMAIL ",
        destination="  SUMIT@EXAMPLE.COM  ",
    )

    assert channel.type == "email"
    assert channel.destination == "sumit@example.com"


def test_unsupported_channel_type_is_rejected():
    with pytest.raises(ValidationError):
        AlertChannelCreate(
            type="sms",
            destination="sumit@example.com",
        )


@pytest.mark.parametrize(
    "email",
    [
        "invalid-email",
        "sumit@",
        "@example.com",
        "sumit@example",
    ],
)
def test_invalid_email_is_rejected(email):
    with pytest.raises(ValidationError):
        AlertChannelCreate(
            type="email",
            destination=email,
        )
