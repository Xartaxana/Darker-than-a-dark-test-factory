"""Страница работы AO3 (/works/{id}) внутри WebView."""
from __future__ import annotations

from framework.web.base_page import BasePage


class WorkPage(BasePage):
    def current_work_id(self) -> str | None:
        url = self.driver.current_url or ""
        import re
        m = re.search(r"/works/(\d+)", url)
        return m.group(1) if m else None

    # `has_badge()` удалён (AT-BUG-004 инкремент 3, правило 9 — тот же класс
    # дефекта, что и `ListingPage.badge_for` до фикса): ссылался на удалённый
    # `selectors.RATING_BADGE`. В отличие от листинга, на work-странице
    # `ao3_bridge.js` вообще не инжектирует Rate-кнопку/бейдж (`applyRatings`
    # проходит только по `li[id^="work_"].work.blurb`, которых на work-странице
    # нет) — рейтинг здесь отражён только нативной Compose-панелью (`RatingMenu`
    # в `MainActivity.kt`), не WebView DOM. Метод был неиспользуемым (`WorkPage`
    # нигде не импортируется) и структурно не мог вернуть True ни при каком
    # состоянии — не просто неверный селектор, а неверная предпосылка.

    def title_text(self) -> str:
        el = self.css("h2.title") if self.exists("h2.title") else None
        return el.text.strip() if el else ""
