"""What is allowed, what is always blocked. Shared so agent and server agree."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

APP_CATALOG: dict[str, tuple[str, ...]] = {
    "VS Code": ("code.exe",),
    "CodeBlocks": ("codeblocks.exe",),
    "Terminal": ("windowsterminal.exe", "cmd.exe", "powershell.exe", "pwsh.exe", "conhost.exe"),
    "Explorer": ("explorer.exe",),
    "Wireshark": ("wireshark.exe",),
    "VMware": ("vmware.exe", "vmplayer.exe", "vmware-vmx.exe"),
    "Notepad": ("notepad.exe", "notepad++.exe"),
}

PRESETS: dict[str, tuple[str, ...]] = {
    "networking": ("VS Code", "CodeBlocks", "Terminal", "Explorer", "Wireshark", "VMware", "Notepad"),
    "programming": ("VS Code", "CodeBlocks", "Terminal", "Explorer", "Notepad"),
}

# Browsers are allowed (PDFs open in Edge) but every site they show is checked.
BROWSERS = frozenset({"chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe"})

ALWAYS_ALLOWED = frozenset({
    "tide-agent.exe", "explorer.exe", "searchhost.exe", "shellexperiencehost.exe",
    "startmenuexperiencehost.exe", "lockapp.exe", "applicationframehost.exe",
    "textinputhost.exe", "systemsettings.exe", "msedgewebview2.exe",
})

DENY_PROCESSES: dict[str, str] = {
    "chatgpt.exe": "ChatGPT", "claude.exe": "Claude", "copilot.exe": "Copilot",
    "cursor.exe": "Cursor", "windsurf.exe": "Windsurf", "ollama.exe": "Ollama",
    "ollama app.exe": "Ollama", "lm studio.exe": "LM Studio", "whatsapp.exe": "WhatsApp",
    "telegram.exe": "Telegram", "discord.exe": "Discord", "anydesk.exe": "AnyDesk",
    "teamviewer.exe": "TeamViewer", "outlook.exe": "Outlook", "olk.exe": "Outlook",
    "slack.exe": "Slack", "zoom.exe": "Zoom",
}

# poe.com is intentionally NOT listed: the demo shows Jev catching it.
DENY_HOSTS: dict[str, str] = {
    "chatgpt.com": "ChatGPT", "chat.openai.com": "ChatGPT", "claude.ai": "Claude",
    "gemini.google.com": "Gemini", "copilot.microsoft.com": "Copilot",
    "perplexity.ai": "Perplexity", "chat.deepseek.com": "DeepSeek", "grok.com": "Grok",
    "meta.ai": "Meta AI", "chat.mistral.ai": "Mistral", "web.whatsapp.com": "WhatsApp",
    "mail.google.com": "Gmail", "outlook.live.com": "Outlook", "drive.google.com": "Drive",
    "classroom.google.com": "Classroom",
}

LOCAL_HOSTS = frozenset({"", "localhost", "127.0.0.1", "newtab", "new-tab-page", "extensions", "settings"})

AI_EXTENSIONS: dict[str, str] = {
    "github.copilot": "GitHub Copilot", "codeium.": "Codeium", "continue.": "Continue",
    "saoudrizwan.claude-dev": "Cline", "tabnine.": "Tabnine", "supermaven.": "Supermaven",
    "amazonwebservices.amazon-q": "Amazon Q", "rooveterinaryinc.roo-cline": "Roo Code",
    "google.geminicodeassist": "Gemini Code Assist",
}

CLIPBOARD_MIN = 200


def host_match(host: str, table: dict[str, str]) -> str | None:
    host = host.lower().strip(".")
    for domain, name in table.items():
        if host == domain or host.endswith("." + domain):
            return name
    return None


def display_app(process: str) -> str:
    p = process.lower()
    for name, procs in APP_CATALOG.items():
        if p in procs:
            return name
    return process[:-4] if p.endswith(".exe") else process


@dataclass(frozen=True)
class Policy:
    apps: tuple[str, ...]
    allowed_processes: frozenset[str]
    server_ip: str = ""
    internet: str = "allowed"          # "allowed" (monitored) | "blocked" (must stay offline)

    @classmethod
    def from_apps(cls, apps: Iterable[str], server_ip: str = "", internet: str = "allowed") -> "Policy":
        apps = tuple(sorted(apps))
        procs = frozenset(p for a in apps for p in APP_CATALOG.get(a, ()))
        return cls(apps=apps, allowed_processes=procs, server_ip=server_ip, internet=internet)

    @property
    def internet_blocked(self) -> bool:
        return self.internet == "blocked"

    def is_allowed_process(self, name: str) -> bool:
        n = name.lower()
        return n in self.allowed_processes or n in ALWAYS_ALLOWED

    def to_dict(self) -> dict[str, Any]:
        return {"apps": list(self.apps), "allowed_processes": sorted(self.allowed_processes),
                "server_ip": self.server_ip, "internet": self.internet}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Policy":
        return cls(apps=tuple(d.get("apps", ())),
                   allowed_processes=frozenset(d.get("allowed_processes", ())),
                   server_ip=d.get("server_ip", ""), internet=d.get("internet", "allowed"))
