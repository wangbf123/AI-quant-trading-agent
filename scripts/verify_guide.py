"""Fast browser acceptance for the interactive project guide; no research jobs."""
import os
from pathlib import Path
import re
import shutil

from playwright.sync_api import expect, sync_playwright


def main():
    artifacts = Path(os.getenv('AQR_QA_DIR', 'data/results/guide-qa'))
    artifacts.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=shutil.which('chromium'), headless=True, args=['--no-sandbox'])
        page = browser.new_page(viewport={'width': 1440, 'height': 1100})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(os.getenv('AQR_TEST_URL', 'http://127.0.0.1:8000'), wait_until='networkidle')
        expect(page.get_by_role('heading', name=re.compile('从一个想法'))).to_be_visible()
        page.get_by_role('button', name='暂停流程演示').click()
        page.get_by_role('button', name='查看经济性失败记忆').click()
        expect(page.locator('.guide-detail-heading h3')).to_have_text('经济性失败记忆')
        expect(page.get_by_role('button', name='查看经济性失败记忆')).to_have_attribute('aria-pressed', 'true')
        page.screenshot(path=str(artifacts / 'guide-desktop.png'), full_page=True, animations='disabled')
        page.get_by_role('tab', name='研究闭环').click()
        page.locator('.guide-journey button').nth(2).click()
        expect(page.locator('.guide-detail-heading h3')).to_have_text('确定性验证')
        page.get_by_role('tab', name='验证协议').click()
        page.locator('.guide-timeline button').nth(3).click()
        expect(page.locator('.guide-window-detail')).to_contain_text('冻结候选后评估一次')
        page.set_viewport_size({'width': 390, 'height': 844})
        page.screenshot(path=str(artifacts / 'guide-protocol-mobile.png'), full_page=True, animations='disabled')
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        page.get_by_role('tab', name='系统架构').click()
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        page.get_by_role('button', name='进入研究工作台').click()
        expect(page.get_by_role('heading', name='让每一次研究，都留下证据。')).to_be_visible()
        page.get_by_role('button', name='项目导览', exact=True).click()
        expect(page.get_by_role('heading', name=re.compile('从一个想法'))).to_be_visible()
        reduced = browser.new_page(reduced_motion='reduce')
        reduced.goto(os.getenv('AQR_TEST_URL', 'http://127.0.0.1:8000'), wait_until='networkidle')
        expect(reduced.get_by_role('button', name=re.compile('流程演示'))).to_be_disabled()
        assert reduced.locator('animateMotion').count() == 0
        assert not errors, errors
        browser.close()
    print('Passed: graph selection, play/pause, loop steps, protocol windows, page navigation, mobile layout, reduced motion, no browser exceptions')


if __name__ == '__main__':
    main()
