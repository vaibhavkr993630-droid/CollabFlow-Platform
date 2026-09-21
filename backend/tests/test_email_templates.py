from email import message_from_bytes
from email.policy import default as default_policy

from app.core import email as email_module
from app.core.email_templates import render_email


def test_render_email_has_button_link_in_both_versions():
    text, html = render_email(
        heading="Reset your password",
        paragraphs=["Hi Ada,"],
        button_label="Reset password",
        button_url="http://localhost:5173/reset-password?token=abc.def",
    )
    assert "Reset password: http://localhost:5173/reset-password?token=abc.def" in text
    assert 'href="http://localhost:5173/reset-password?token=abc.def"' in html
    assert "Reset password</a>" in html


def test_render_email_escapes_user_controlled_text():
    text, html = render_email(
        heading="<script>alert(1)</script>",
        paragraphs=["Task '<img src=x onerror=alert(1)>' is due"],
        button_label="Open",
        button_url='http://x/"><script>',
    )
    assert "<script>" not in html
    assert "<img" not in html
    assert "&lt;img" in html
    # The plain-text version is not HTML, so it carries the text verbatim.
    assert "<img src=x" in text


def test_send_email_is_multipart_alternative_when_html_given(monkeypatch):
    captured = {}

    class FakeSMTP:
        def __init__(self, host, port):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def send_message(self, message):
            captured["raw"] = message.as_bytes()

    monkeypatch.setattr(email_module.smtplib, "SMTP", FakeSMTP)
    email_module.send_email(
        to_email="a@example.com", subject="Hi", body="plain text", html_body="<b>rich</b>"
    )

    parsed = message_from_bytes(captured["raw"], policy=default_policy)
    assert parsed.get_content_type() == "multipart/alternative"
    assert "plain text" in parsed.get_body(preferencelist=("plain",)).get_content()
    assert "<b>rich</b>" in parsed.get_body(preferencelist=("html",)).get_content()


def test_send_email_stays_plain_without_html(monkeypatch):
    captured = {}

    class FakeSMTP:
        def __init__(self, host, port):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def send_message(self, message):
            captured["raw"] = message.as_bytes()

    monkeypatch.setattr(email_module.smtplib, "SMTP", FakeSMTP)
    email_module.send_email(to_email="a@example.com", subject="Hi", body="only text")

    parsed = message_from_bytes(captured["raw"], policy=default_policy)
    assert parsed.get_content_type() == "text/plain"
