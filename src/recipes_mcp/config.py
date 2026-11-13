from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SearchMode = Literal["auto", "wordpress", "blogger", "searxng"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mcp_path_token: str
    searxng_url: str = "http://searxng:8081"
    public_host: str = "recipesmcp.com"
    log_level: str = "INFO"
    blogs_file: Path = Path("blogs.yaml")
    port: int = 8001

    @field_validator("mcp_path_token")
    @classmethod
    def _token_strong_enough(cls, v: str) -> str:
        if len(v) < 32 or not v.isalnum():
            raise ValueError("MCP_PATH_TOKEN must be 32+ alphanumeric characters")
        return v


class Blog(BaseModel):
    name: str
    domain: str
    search: SearchMode = "auto"


def load_blogs(path: Path) -> list[Blog]:
    data = yaml.safe_load(path.read_text())
    return [Blog(**b) for b in data["blogs"]]


def host_matches(host: str, domain: str) -> bool:
    host = host.lower().rstrip(".")
    return host == domain or host.endswith("." + domain)


def find_blog(blogs: list[Blog], host: str) -> Blog | None:
    return next((b for b in blogs if host_matches(host, b.domain)), None)
