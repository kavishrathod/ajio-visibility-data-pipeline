"""Delivery channels: file sink, SMTP with credentials from the environment, SMTP failure handling."""
import smtplib

from src.monitoring import mailer as mailer_module
from src.monitoring.mailer import Mailer


def test_file_sink_writes_an_eml(tmp_path, monkeypatch):
    monkeypatch.delenv("ALERT_SINK", raising=False)
    monkeypatch.setenv("ALERT_OUTBOX_DIR", str(tmp_path / "out"))
    assert Mailer(tmp_path).send("[AJIO VISIBILITY][WARNING] Test", "hello body") is True
    files = list((tmp_path / "out").glob("*.eml"))
    assert len(files) == 1
    text = files[0].read_text()
    assert "Subject: [AJIO VISIBILITY][WARNING] Test" in text and "hello body" in text


def test_smtp_uses_credentials_from_environment(tmp_path, monkeypatch):
    seen = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            seen["addr"] = (host, port)
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self): seen["tls"] = True
        def login(self, user, password): seen["login"] = (user, password)
        def send_message(self, message): seen["subject"] = message["Subject"]

    monkeypatch.setattr(mailer_module.smtplib, "SMTP", FakeSMTP)
    for key, value in {"ALERT_SINK": "smtp", "SMTP_HOST": "mail.test", "SMTP_PORT": "2525", "SMTP_USER": "u1",
                       "SMTP_PASSWORD": "p1", "SMTP_STARTTLS": "true", "ALERT_OUTBOX_DIR": str(tmp_path / "out")}.items():
        monkeypatch.setenv(key, value)
    assert Mailer(tmp_path).send("subject-x", "body") is True
    assert seen == {"addr": ("mail.test", 2525), "tls": True, "login": ("u1", "p1"), "subject": "subject-x"}


def test_smtp_failure_returns_false_and_still_keeps_a_file_copy(tmp_path, monkeypatch):
    def refuse(*args, **kwargs):
        raise ConnectionRefusedError("nobody is listening")

    monkeypatch.setattr(mailer_module.smtplib, "SMTP", refuse)
    monkeypatch.setenv("ALERT_SINK", "smtp")
    monkeypatch.setenv("SMTP_HOST", "127.0.0.1")
    monkeypatch.setenv("ALERT_OUTBOX_DIR", str(tmp_path / "out"))
    assert Mailer(tmp_path).send("s", "b") is False
    assert len(list((tmp_path / "out").glob("*.eml"))) == 1
