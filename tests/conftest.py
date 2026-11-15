import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as playwright:
        try:
            chrome = playwright.chromium.launch(channel="chrome", headless=True)
        except PlaywrightError as err:
            pytest.skip(f"Google Chrome isn't available here: {err}")
        yield chrome
        chrome.close()


@pytest.fixture
def page(browser):
    tab = browser.new_page()
    yield tab
    tab.close()
