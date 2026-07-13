"""
PayrollPro (Python Edition) — Application Settings
====================================================
Centralised, persisted configuration for:
  * Database backend  — SQLite (zero-config, file based) OR
                         MySQL/MariaDB via XAMPP (host/port/db/user/pass)
  * Email (SMTP)       — mirrors includes/config.php MAIL_* constants
  * SMS (Semaphore/Twilio) — mirrors includes/config.php SMS_*/TWILIO_* constants
  * OTP / passcode policy

Settings are stored as a single JSON file so the whole app is portable —
copy the folder, keep your settings. On first run we create sane
defaults (SQLite database living next to the app).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

APP_NAME = "PayrollPro"
APP_VERSION = "7.0.0-python"

# Root folder of the application (…/payrollpro)
APP_ROOT = Path(__file__).resolve().parent.parent

# Where user data / settings live. Kept inside the app folder so the
# whole thing stays portable (copy folder -> copy install).
DATA_DIR = APP_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

SETTINGS_FILE = DATA_DIR / "settings.json"
DEFAULT_SQLITE_PATH = DATA_DIR / "payroll_system.db"

LOG_DIR = APP_ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class DatabaseConfig:
    # backend: "sqlite" or "mysql"
    backend: str = "sqlite"

    # SQLite
    sqlite_path: str = str(DEFAULT_SQLITE_PATH)

    # MySQL / MariaDB (XAMPP)
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_db: str = "payroll_db"
    mysql_user: str = "root"
    mysql_password: str = ""
    mysql_charset: str = "utf8mb4"


@dataclass
class MailConfig:
    enabled: bool = False
    host: str = "smtp.gmail.com"
    port: int = 587
    encryption: str = "tls"          # 'tls' or 'ssl'
    username: str = "your_email@gmail.com"
    password: str = ""               # Gmail App Password (16 chars)
    from_email: str = "your_email@gmail.com"
    from_name: str = "PayrollPro System"
    company_name: str = "PayrollPro"


@dataclass
class SmsConfig:
    enabled: bool = False
    provider: str = "semaphore"      # 'semaphore' or 'twilio'
    api_key: str = "YOUR_SEMAPHORE_API_KEY_HERE"
    sender_name: str = "PAYROLL"
    # Twilio alternative
    twilio_sid: str = "YOUR_TWILIO_ACCOUNT_SID"
    twilio_token: str = "YOUR_TWILIO_AUTH_TOKEN"
    twilio_from: str = "+1XXXXXXXXXX"


@dataclass
class OtpConfig:
    expiry_minutes: int = 10
    otp_length: int = 6
    passcode_length: int = 8


@dataclass
class AttendanceConfig:
    # Used by core.attendance_service to auto-flag "late" and compute
    # overtime from raw time-in/time-out timestamps.
    shift_start: str = "08:00"       # 24h "HH:MM"
    shift_end: str = "17:00"
    grace_minutes: int = 10
    standard_hours_per_day: float = 8.0


@dataclass
class AppSettings:
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    mail: MailConfig = field(default_factory=MailConfig)
    sms: SmsConfig = field(default_factory=SmsConfig)
    otp: OtpConfig = field(default_factory=OtpConfig)
    attendance: AttendanceConfig = field(default_factory=AttendanceConfig)
    theme: str = "classic"
    max_failed_logins: int = 3
    reset_default_password: str = "emp123"
    admin_default_password: str = "admin123"

    # ---------------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "database": asdict(self.database),
            "mail": asdict(self.mail),
            "sms": asdict(self.sms),
            "otp": asdict(self.otp),
            "attendance": asdict(self.attendance),
            "theme": self.theme,
            "max_failed_logins": self.max_failed_logins,
            "reset_default_password": self.reset_default_password,
            "admin_default_password": self.admin_default_password,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AppSettings":
        s = cls()
        if "database" in d:
            s.database = DatabaseConfig(**{**asdict(s.database), **d["database"]})
        if "mail" in d:
            s.mail = MailConfig(**{**asdict(s.mail), **d["mail"]})
        if "sms" in d:
            s.sms = SmsConfig(**{**asdict(s.sms), **d["sms"]})
        if "otp" in d:
            s.otp = OtpConfig(**{**asdict(s.otp), **d["otp"]})
        if "attendance" in d:
            s.attendance = AttendanceConfig(**{**asdict(s.attendance), **d["attendance"]})
        s.theme = d.get("theme", s.theme)
        s.max_failed_logins = d.get("max_failed_logins", s.max_failed_logins)
        s.reset_default_password = d.get("reset_default_password", s.reset_default_password)
        s.admin_default_password = d.get("admin_default_password", s.admin_default_password)
        return s


class SettingsManager:
    """Loads/saves AppSettings to a JSON file. Singleton-style access
    via `get_settings()` / `save_settings()` below."""

    def __init__(self, path: Path = SETTINGS_FILE):
        self.path = path
        self._settings: Optional[AppSettings] = None

    def load(self) -> AppSettings:
        if self._settings is not None:
            return self._settings
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._settings = AppSettings.from_dict(data)
            except Exception:
                self._settings = AppSettings()
        else:
            self._settings = AppSettings()
            self.save(self._settings)
        return self._settings

    def save(self, settings: Optional[AppSettings] = None) -> None:
        settings = settings or self._settings
        if settings is None:
            return
        self._settings = settings
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(settings.to_dict(), f, indent=2)


_manager = SettingsManager()


def get_settings() -> AppSettings:
    return _manager.load()


def save_settings(settings: AppSettings) -> None:
    _manager.save(settings)


def sqlalchemy_url(cfg: Optional[DatabaseConfig] = None) -> str:
    """Build a SQLAlchemy connection URL for the currently configured backend."""
    cfg = cfg or get_settings().database
    if cfg.backend == "mysql":
        # PyMySQL driver — pure-python, no compiled deps, works great with XAMPP's MariaDB.
        pw = cfg.mysql_password.replace("@", "%40")
        return (
            f"mysql+pymysql://{cfg.mysql_user}:{pw}@{cfg.mysql_host}:{cfg.mysql_port}"
            f"/{cfg.mysql_db}?charset={cfg.mysql_charset}"
        )
    # SQLite default
    path = cfg.sqlite_path or str(DEFAULT_SQLITE_PATH)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    return f"sqlite:///{path}"
