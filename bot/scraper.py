from playwright.async_api import async_playwright

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

# 캘린더 페이지의 강좌 선택 드롭다운에서 course_id -> 과목명 동적 추출
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


def _classify(title: str) -> str:
    """이벤트 타입 분류."""
    t = title.lower()
    if "progress stop" in t or "progress start" in t:
        return "video"
    if "closes" in t or "퀴즈" in t:
        return "quiz"
    if title == "마감 기한":
        return "assignment"
    return "other"


def _clean_title(title: str, desc: str) -> str:
    """Progress stop/start 제거, 마감 기한은 설명 첫 줄로 대체."""
    if title == "마감 기한":
        first_line = desc.split("\n")[0].strip() if desc else ""
        return first_line or "과제 제출"
    # "xxx : Progress stop/start" → "xxx"
    for suffix in (" : Progress stop", " : Progress start"):
        if title.endswith(suffix):
            title = title[: -len(suffix)]
    # "퀴즈: xxx closes" → "퀴즈: xxx"
    if title.endswith(" closes"):
        title = title[: -len(" closes")]
    # URL 인코딩된 + 제거
    title = title.replace("+", " ")
    # 말줄임표 제거
    if title.endswith(".."):
        title = title[:-2].rstrip()
    return title


async def get_upcoming_events(ecampus_id: str, ecampus_pw: str) -> dict:
    """
    ecampus 로그인 후 예정된 이벤트를 반환.
    반환값: {"assignments": [...], "quizzes": [...], "videos": [...]}
    각 항목: {course, title, date, desc, url}
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # 로그인
        await page.goto("https://ecampus.sejong.ac.kr/login/index.php")
        await page.wait_for_load_state("networkidle")
        await page.locator('input[name="username"]').first.fill(ecampus_id)
        await page.locator('input[name="password"]').first.fill(ecampus_pw)
        await page.locator('input[name="loginbutton"]').first.click()
        await page.wait_for_load_state("networkidle")

        # 캘린더 upcoming
        await page.goto("https://ecampus.sejong.ac.kr/calendar/view.php?view=upcoming")
        await page.wait_for_load_state("networkidle")

        # 과목 목록 + 이벤트 동시에 추출
        course_map: dict = await page.evaluate(_COURSE_MAP_JS)
        raw = await page.evaluate(_SCRAPE_JS)
        await browser.close()

    assignments, quizzes, videos = [], [], []

    for e in raw:
        kind = _classify(e["title"])
        course = course_map.get(e["courseId"], f"과목({e['courseId']})")
        clean = _clean_title(e["title"], e["desc"])
        item = {
            "course": course,
            "title": clean,
            "date": e["date"].strip(),
            "desc": e["desc"].split("\n")[0].strip() if kind != "assignment" else "",
            "url": e["url"],
        }
        if kind == "assignment":
            assignments.append(item)
        elif kind == "quiz":
            quizzes.append(item)
        elif kind == "video":
            videos.append(item)

    return {"assignments": assignments, "quizzes": quizzes, "videos": videos}
