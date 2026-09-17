"""Generic pagination math, decoupled from SQL and from Telegram.

Handlers/services pass `limit`/`offset` computed here straight into the
repository's `LIMIT`/`OFFSET` query — nothing is ever loaded into memory in
full just to be sliced client-side.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Page:
    page: int  # zero-based
    page_size: int
    total_items: int

    @property
    def total_pages(self) -> int:
        if self.total_items == 0:
            return 1
        return (self.total_items + self.page_size - 1) // self.page_size

    @property
    def offset(self) -> int:
        return self.page * self.page_size

    @property
    def has_prev(self) -> bool:
        return self.page > 0

    @property
    def has_next(self) -> bool:
        return self.page < self.total_pages - 1

    @property
    def clamped(self) -> "Page":
        """Return a copy with `page` clamped into the valid [0, total_pages-1] range.

        Guards against a stale "page" value in old callback_data (e.g. an
        admin taps "Next" right as the last participant on that page gets
        deleted by someone else).
        """
        max_page = max(self.total_pages - 1, 0)
        clamped_page = min(max(self.page, 0), max_page)
        if clamped_page == self.page:
            return self
        return Page(page=clamped_page, page_size=self.page_size, total_items=self.total_items)

    def header(self, *, label: str = "страница") -> str:
        return f"{label} {self.page + 1}/{self.total_pages}"
