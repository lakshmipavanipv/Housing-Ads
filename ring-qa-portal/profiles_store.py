"""Ring-model profiles (UUID variables) stored as JSON files in profiles/."""
import json
import re
from pathlib import Path

DEFAULT = "body_and_soul"


class ProfileStore:
    def __init__(self, folder: Path):
        self.dir = Path(folder)
        self.dir.mkdir(exist_ok=True)
        marker = self.dir / "_active.txt"
        name = marker.read_text().strip() if marker.exists() else DEFAULT
        if not (self.dir / f"{name}.json").exists():
            name = DEFAULT
        self.load(name)

    @staticmethod
    def slug(name):
        s = re.sub(r"[^a-z0-9_]+", "_", name.strip().lower()).strip("_")
        if not s:
            raise ValueError("profile name is empty")
        return s

    def list(self):
        return sorted(p.stem for p in self.dir.glob("*.json"))

    def load(self, name):
        name = self.slug(name)
        self.active = json.loads((self.dir / f"{name}.json").read_text())
        self.active_name = name
        (self.dir / "_active.txt").write_text(name)
        return self.active

    def save(self, data, name=None):
        name = self.slug(name or self.active_name)
        if not isinstance(data.get("vars"), dict):
            raise ValueError("profile must contain 'vars'")
        (self.dir / f"{name}.json").write_text(json.dumps(data, indent=2))
        return self.load(name)
