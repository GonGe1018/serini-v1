import logging
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

logger = logging.getLogger(__name__)

_SCRAPE_JS = """
() => {
    var events = [];
    var els = document.querySelectorAll('.event');
    for (var i = 0; i < els.length; i++) {
        var el = els[i];
        var titleEl = el.querySelector('h3.name');
        var dateEl = el.querySelector('.calendar-date');
        var descEl = el.querySelector('.calendar-body');
        var html = el.innerHTML;
        var urlMatch = html.match(/href="(https:\\/\\/ecampus\\.sejong\\.ac\\.kr\\/mod\\/[^"]+)"/);
        events.push({
            courseId: el.getAttribute('data-course-id'),
            title: titleEl ? titleEl.textContent.trim() : '',
            date: dateEl ? dateEl.textContent.trim() : '',
            desc: descEl ? descEl.innerText.trim().substring(0, 200) : '',
            url: urlMatch ? urlMatch[1] : ''
        });
    }
    return events;
}
"""

_COURSE_MAP_JS = """
() => {
    var map = {};
    var opts = document.querySelectorAll('select.cal_courses_flt option');
    for (var i = 0; i < opts.length; i++) {
        var val = opts[i].value;
        var text = opts[i].textContent.trim();
        if (val && val !== '1') {
            var name = text.replace(/\\s*\\(\\S+\\)\\s*$/, '').trim();
            map[val] = name;
        }
    }
    return map;
}
"""

_TIMEOUT = 30000  # 30초


def _classify(title: str) -> str:
    t = title.lower()
    if "progress stop" in t or "progress start" in t:
        return "video"
    if "closes" in t or "퀴즈" in t:
        return "quiz"
    if title == "마감 기한":
        return "assignment"
    return "other"


def _clean_title(title: str, desc: str) -> str:
    if title == "마감 기한":
        first_line = desc.split("\n")[0].strip() if desc else ""
        return first_line or "과제 제출"
    for suffix in (" : Progress stop", " : Progress start"):
        if title.endswith(suffix):
            title = title[: -len(suffix)]
    if title.endswith(" closes"):
        title = title[: -len(" closes")]
    title = title.replace("+", " ")
    if title.endswith(".."):
        title = title[:-2].rstrip()
    return title


async def get_upcoming_events(ecampus_id: str, ecampus_pw: str) -> dict:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()

            await page.goto(
                "https://ecampus.sejong.ac.kr/login/index.php",
                timeout=_TIMEOUT,
                wait_until="networkidle",
            )
            await page.locator('input[name="username"]').first.fill(ecampus_id)
            await page.locator('input[name="password"]').first.fill(ecampus_pw)
            await page.locator('input[name="loginbutton"]').first.click()
            await page.wait_for_load_state("networkidle", timeout=_TIMEOUT)

            if "login" in page.url:
                logger.warning("ecampus 로그인 실패 (id=%s)", ecampus_id)
                return {"assignments": [], "quizzes": [], "videos": []}

            await page.goto(
                "https://ecampus.sejong.ac.kr/calendar/view.php?view=upcoming",
                timeout=_TIMEOUT,
                wait_until="networkidle",
            )

            course_map: dict = await page.evaluate(_COURSE_MAP_JS)
            raw: list = await page.evaluate(_SCRAPE_JS)
        except PlaywrightTimeout:
            logger.exception("ecampus 타임아웃 (id=%s)", ecampus_id)
            return {"assignments": [], "quizzes": [], "videos": []}
        except Exception:
            logger.exception("ecampus 스크래핑 실패 (id=%s)", ecampus_id)
            return {"assignments": [], "quizzes": [], "videos": []}
        finally:
            await browser.close()

    assignments, quizzes, videos = [], [], []

    for e in raw:
        kind = _classify(e.get("title", ""))
        course = course_map.get(e.get("courseId"), f"과목({e.get('courseId', '?')})")
        clean = _clean_title(e.get("title", ""), e.get("desc", ""))
        item = {
            "course": course,
            "title": clean,
            "date": e.get("date", "").strip(),
            "desc": e.get("desc", "").split("\n")[0].strip() if kind != "assignment" else "",
            "url": e.get("url", ""),
        }
        if kind == "assignment":
            assignments.append(item)
        elif kind == "quiz":
            quizzes.append(item)
        elif kind == "video":
            videos.append(item)

    return {"assignments": assignments, "quizzes": quizzes, "videos": videos}
