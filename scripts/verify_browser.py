"""Browser acceptance against a running local API; executes real Qlib jobs."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil

import httpx
from playwright.sync_api import expect, sync_playwright


def main():
    url = os.getenv("AQR_TEST_URL", "http://127.0.0.1:8000")
    artifacts = Path(os.getenv("AQR_QA_DIR", "data/results/browser-qa"))
    artifacts.mkdir(parents=True, exist_ok=True)
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.getenv("AQR_CHROMIUM_BINARY") or shutil.which("chromium"), headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1440, "height": 1100}, device_scale_factor=1)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(url, wait_until="networkidle")
        if page.get_by_role("button", name="进入研究工作台").is_visible():
            page.get_by_role("button", name="进入研究工作台").click()
        expect(page.get_by_role("heading", name="让每一次研究，都留下证据。")).to_be_visible()
        expect(page.get_by_role("button", name="启动本地演示研究")).to_be_enabled()
        page.get_by_label("每组实验预算").fill("2")
        page.get_by_label("运行等预算消融（两组实验）").check()
        with page.expect_response(lambda response: response.url.endswith("/api/v1/research/demo") and response.request.method == "POST") as created:
            page.get_by_role("button", name="启动本地演示研究").click()
        payload = created.value.json()
        assert payload["success"], payload
        protocol_id = payload["data"]["protocol"]["id"]
        freeze = page.get_by_role("button", name="冻结候选").first
        expect(freeze).to_be_enabled(timeout=180_000)
        page.screenshot(path=str(artifacts / "validation.png"), full_page=True, animations="disabled")
        freeze.click()
        final = page.get_by_role("button", name="评估封存样本外")
        expect(final).to_be_enabled()
        final.click()
        expect(page.get_by_role("dialog")).to_be_visible()
        page.get_by_role("button", name="确认评估一次").click()
        expect(page.get_by_text("研究已封存", exact=True).first).to_be_visible(timeout=90_000)
        expect(final).to_be_disabled()
        with page.expect_download() as download:
            page.get_by_role("button", name="证据包").click()
        export_path = artifacts / "research-export.json"
        download.value.save_as(export_path)
        exported = json.loads(export_path.read_text())
        assert exported["state"] == "finalized"
        result = exported["result"]
        assert result["holdout"]["equity"]
        assert result["ablation"]["with_memory"]["evaluations"] == 2
        assert result["ablation"]["without_memory"]["evaluations"] == 2
        assert result["provenance"]["source"] == "synthetic"
        assert all(memory["source_split"] == "validation" for memory in result["memories"])
        with httpx.Client(base_url=url, trust_env=False) as client:
            repeated = client.post(f"/api/v1/research/protocols/{protocol_id}/finalize")
            assert repeated.status_code == 409, repeated.text
        page.screenshot(path=str(artifacts / "completed-desktop.png"), full_page=True, animations="disabled")
        page.set_viewport_size({"width": 390, "height": 844})
        page.screenshot(path=str(artifacts / "completed-mobile.png"), full_page=True, animations="disabled")
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "Mobile viewport overflows"
        assert not errors, errors
        browser.close()
    print(json.dumps({"status": "passed", "protocol_id": protocol_id, "validated": ["UI research submission", "four real Qlib validation trials", "equal-budget ablation", "candidate freeze", "real final holdout", "duplicate-finalization rejection", "evidence download", "mobile layout", "no browser exceptions"], "artifacts": str(artifacts)}, indent=2))


if __name__ == "__main__":
    main()
