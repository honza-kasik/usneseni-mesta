from __future__ import annotations

from typing import Tuple


def slug_from_id(resolution_id: str) -> str:
    return resolution_id.replace("/", "-")


def ro_slug_from_id(opatreni_id: str) -> str:
    return opatreni_id.replace("/", "-")


def ro_url(opatreni_id: str) -> str:
    return f"/rozpoctova-opatreni/{ro_slug_from_id(opatreni_id)}/"


def rz_anchor(budget_change_id: str) -> str:
    return "rz-" + budget_change_id.replace("/", "-").lower()


def resolution_url(resolution_id: str) -> str:
    slug = slug_from_id(resolution_id)
    year = resolution_id.split("/")[-1]
    return f"/usneseni/{year}/{slug}/"


def meeting_from_id(rid: str) -> Tuple[str, str, str]:
    org, _, meeting, year = rid.split("/")
    return org, meeting, year
