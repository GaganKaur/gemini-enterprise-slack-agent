# /// script
# dependencies = [
#   "playwright>=1.40.0",
#   "httpx>=0.25.0",
#   "google-auth>=2.23.0",
#   "matplotlib>=3.8.0",
#   "numpy>=1.26.0",
# ]
# ///
import asyncio
import json
import time
import uuid
import httpx
import google.auth
import os
import sys
import datetime
import argparse
import traceback
import re
from google.auth.transport.requests import Request
from playwright.async_api import async_playwright

sys.path.append(os.path.dirname(os.path.abspath(__file__)))


def get_credentials():
    credentials, project = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    if not credentials.valid:
        credentials.refresh(Request())
    return credentials

def get_stats(data_list):
    if not data_list:
        return None, None, None, None, None, None, None
    s_min = min(data_list)
    s_max = max(data_list)
    s_avg = sum(data_list) / len(data_list)
    sorted_data = sorted(data_list)
    
    def get_percentile(p):
        idx = int(len(sorted_data) * p)
        return sorted_data[min(idx, len(sorted_data) - 1)]
        
    s_p50 = get_percentile(0.50)
    s_p90 = get_percentile(0.90)
    s_p95 = get_percentile(0.95)
    s_p99 = get_percentile(0.99)
    return s_min, s_p50, s_p90, s_p95, s_p99, s_max, s_avg

async def run_async_stream_test(client, credentials, project_id, engine_id, scenario, query_text):
    base_url = "https://discoveryengine.googleapis.com/v1alpha"
    url = f"{base_url}/projects/{project_id}/locations/global/collections/default_collection/engines/{engine_id}/assistants/default_assistant:streamAssist"
    
    trace_id = uuid.uuid4().hex
    headers = {
        "Authorization": f"Bearer {credentials.token}",
        "Content-Type": "application/json",
        "X-Goog-User-Project": project_id,
        "x-cloud-trace-context": f"{trace_id}/0;o=1"
    }
    payload = {
        "query": {"text": query_text},
        "session": f"projects/{project_id}/locations/global/collections/default_collection/engines/{engine_id}/sessions/-",
    }
    if "payload" in scenario:
        payload.update(scenario["payload"])
        if "agentsSpec" not in payload:
            target_agent_id = scenario.get("agent_id", "core_assistant")
            payload["agentsSpec"] = {
                "agentSpecs": [{"agentId": target_agent_id}]
            }
    else:
        # Fallback to defaults
        target_agent_id = scenario.get("agent_id", "core_assistant")
        payload["agentsSpec"] = {
            "agentSpecs": [
                {
                    "agentId": target_agent_id
                }
            ]
        }
        payload["toolsSpec"] = {
            "vertexAiSearchSpec": {}
        }
        if scenario.get("skip_classifier", True):
            payload["assistSkippingMode"] = "REQUEST_ASSIST"
        
    start_time = time.time()
    ttft = None
    response_text = ""
    status_code = None
    
    try:
        async with client.stream("POST", url, json=payload, headers=headers) as response:
            status_code = response.status_code
            if response.status_code != 200:
                body = await response.aread()
                return {
                    "status_code": response.status_code,
                    "error": f"Status {response.status_code}: {body.decode('utf-8')}",
                    "ttft": None,
                    "ttlt": time.time() - start_time,
                    "response_text": "",
                    "generation_speed": 0.0,
                    "trace_id": trace_id
                }
                
            buffer = ""
            decoder = json.JSONDecoder()
            async for chunk in response.aiter_text():
                buffer += chunk
                buffer = buffer.lstrip()
                if buffer.startswith('['): buffer = buffer[1:].lstrip()
                if buffer.startswith(','): buffer = buffer[1:].lstrip()
                
                while buffer:
                    try:
                        obj, index = decoder.raw_decode(buffer)
                        buffer = buffer[index:].lstrip()
                        if buffer.startswith(','): buffer = buffer[1:].lstrip()
                        if buffer.startswith(']'): buffer = buffer[1:].lstrip()
                        
                        if ttft is None:
                            ttft = time.time() - start_time
                            
                        # Extract stream text
                        answer = obj.get("answer", {})
                        replies = answer.get("replies", [])
                        if replies:
                            content = replies[0].get("groundedContent", {}).get("content", {})
                            text = content.get("text", "")
                            if text:
                                if text.startswith(response_text):
                                    response_text = text
                                else:
                                    response_text += text
                    except json.JSONDecodeError:
                        break
                        
        end_time = time.time() - start_time
        generation_speed = len(response_text) / (end_time - ttft) if (ttft is not None and (end_time - ttft) > 0) else 0.0
        return {
            "status_code": status_code,
            "ttft": ttft,
            "ttlt": end_time,
            "trace_id": trace_id,
            "response_text": response_text,
            "generation_speed": generation_speed,
            "error": None
        }
    except Exception as e:
        return {
            "status_code": status_code or 500,
            "error": str(e),
            "ttft": None,
            "ttlt": time.time() - start_time,
            "response_text": "",
            "generation_speed": 0.0,
            "trace_id": trace_id
        }

async def run_async_sync_test(client, credentials, project_id, engine_id, scenario, query_text):
    base_url = "https://discoveryengine.googleapis.com/v1alpha"
    url = f"{base_url}/projects/{project_id}/locations/global/collections/default_collection/engines/{engine_id}/assistants/default_assistant:assist"
    
    trace_id = uuid.uuid4().hex
    headers = {
        "Authorization": f"Bearer {credentials.token}",
        "Content-Type": "application/json",
        "X-Goog-User-Project": project_id,
        "x-cloud-trace-context": f"{trace_id}/0;o=1"
    }
    payload = {
        "query": {"text": query_text},
        "session": f"projects/{project_id}/locations/global/collections/default_collection/engines/{engine_id}/sessions/-"
    }
    if "payload" in scenario:
        payload.update(scenario["payload"])
    else:
        # Fallback to defaults
        if scenario.get("skip_classifier", True):
            payload["assistSkippingMode"] = "REQUEST_ASSIST"
        
    start_time = time.time()
    status_code = None
    
    try:
        response = await client.post(url, json=payload, headers=headers)
        status_code = response.status_code
        end_time = time.time() - start_time
        if response.status_code != 200:
            return {
                "status_code": response.status_code,
                "error": f"Status {response.status_code}: {response.text}",
                "ttft": None,
                "ttlt": end_time,
                "response_text": "",
                "generation_speed": 0.0,
                "trace_id": trace_id
            }
            
        res_json = response.json()
        answer = res_json.get("answer", {})
        response_text = answer.get("answerText", "")
        if not response_text:
            replies = answer.get("replies", [])
            if replies:
                response_text = replies[0].get("groundedContent", {}).get("content", {}).get("text", "")
                
        generation_speed = len(response_text) / end_time if end_time > 0 else 0.0
        return {
            "status_code": response.status_code,
            "ttft": None,
            "ttlt": end_time,
            "trace_id": trace_id,
            "response_text": response_text,
            "generation_speed": generation_speed,
            "error": None
        }
    except Exception as e:
        return {
            "status_code": status_code or 500,
            "error": str(e),
            "ttft": None,
            "ttlt": time.time() - start_time,
            "response_text": "",
            "generation_speed": 0.0,
            "trace_id": trace_id
        }

async def run_ui_test(context, base_url, query_text, run_id, run_dir, scenario_name="ui"):
    page = None
    console_logs = []
    status_code = 200
    start_time = time.time()
    
    try:
        page = await context.new_page()
        
        # Subscribe to console log events
        page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))
        
        trace_id = None
        async def handle_request(req):
            nonlocal trace_id
            if "assistants/default_assistant:" in req.url:
                headers = await req.all_headers()
                trace_context = headers.get("x-cloud-trace-context", "")
                if trace_context:
                    trace_id = trace_context.split("/")[0]
        
        page.on("request", handle_request)
        await page.goto(base_url, timeout=60000)
        await page.wait_for_selector(".ProseMirror", timeout=60000)
        
        # Check and dismiss welcome modal if present
        dismiss_modal_js = """
        () => {
            const findTextInShadows = (root, text) => {
                const all = root.querySelectorAll('*');
                for (const el of all) {
                    if (el.textContent.trim().toLowerCase() === text.toLowerCase()) {
                        let hasChildMatch = false;
                        for (const child of el.children) {
                            if (child.textContent.trim().toLowerCase() === text.toLowerCase()) {
                                hasChildMatch = true;
                                break;
                            }
                        }
                        if (el.shadowRoot) {
                            const found = findTextInShadows(el.shadowRoot, text);
                            if (found) return found;
                        }
                        if (!hasChildMatch) {
                            return el;
                        }
                    }
                    if (el.shadowRoot) {
                        const found = findTextInShadows(el.shadowRoot, text);
                        if (found) return found;
                    }
                }
                return null;
            };

            const btn = findTextInShadows(document, "Get started");
            if (btn) {
                btn.click();
                return true;
            }
            return false;
        }
        """
        dismissed = await page.evaluate(dismiss_modal_js)
        if dismissed:
            await asyncio.sleep(2.0)

        # Click the Preview tab button ONLY if it exists in the header shadow DOM
        click_preview_tab_js = """
        () => {
            const findInShadows = (root, selector) => {
                const el = root.querySelector(selector);
                if (el) return el;
                const all = root.querySelectorAll('*');
                for (const child of all) {
                    if (child.shadowRoot) {
                        const found = findInShadows(child.shadowRoot, selector);
                        if (found) return found;
                    }
                }
                return null;
            };
            const header = findInShadows(document, 'ucs-agent-header');
            if (header && header.shadowRoot) {
                const previewTab = header.shadowRoot.querySelector('[data-test-id="preview-tab"]');
                if (previewTab) {
                    previewTab.click();
                    return true;
                }
            }
            return false;
        }
        """
        did_click = await page.evaluate(click_preview_tab_js)
        if did_click:
            # Wait for the preview panel to animate open and load
            await asyncio.sleep(2.0)

        # Focus and natively fill query using Playwright to trigger framework states correctly (handles concurrency focus isolation)
        input_locator = page.locator(".ProseMirror")
        await input_locator.fill(query_text)
        
        # Resolve target send button
        send_locator = page.locator("md-icon-button.send-button")
        await send_locator.wait_for(state="visible", timeout=10000)

        poll_js = """
        () => {
            const findInShadows = (root, selector) => {
                const el = root.querySelector(selector);
                if (el) return el;
                const all = root.querySelectorAll('*');
                for (const child of all) {
                    if (child.shadowRoot) {
                        const found = findInShadows(child.shadowRoot, selector);
                        if (found) return found;
                    }
                }
                return null;
            };

            const getTurnsCount = () => {
                const conversation = findInShadows(document, 'ucs-conversation');
                const mainDiv = conversation ? conversation.shadowRoot.querySelector('.main') : null;
                const turns = mainDiv ? mainDiv.querySelectorAll('.turn') : [];
                return turns.length;
            };

            const initialTurnsCount = getTurnsCount();
            const sendBtn = findInShadows(document, 'md-icon-button.send-button');
            
            let clickTime = null;
            if (sendBtn) {
                sendBtn.addEventListener('click', () => {
                    clickTime = performance.now();
                }, { once: true });
            }

            return new Promise((resolve) => {
                let ttft = null;
                let ttlt = null;
                let lastText = "";
                let lastChangeTime = performance.now();
                const startTime = performance.now();
                const getStartTime = () => clickTime || startTime;
                const pollInterval = 50;
                const timeoutLimit = 90000;

                const check = setInterval(() => {
                    const tStart = getStartTime();
                    const elapsed = performance.now() - tStart;
                    if (elapsed > timeoutLimit) {
                        clearInterval(check);
                        resolve({ error: 'Timeout waiting for response', ttft, partial_ttlt: (performance.now() - tStart) / 1000 });
                        return;
                    }

                    const conversation = findInShadows(document, 'ucs-conversation');
                    const mainDiv = conversation ? conversation.shadowRoot.querySelector('.main') : null;
                    const currentTurns = mainDiv ? mainDiv.querySelectorAll('.turn') : [];
                    if (currentTurns.length <= initialTurnsCount) {
                        return;
                    }

                    const lastTurn = currentTurns[currentTurns.length - 1];
                    const summaryDiv = findInShadows(lastTurn, '.summary');
                    const footer = findInShadows(lastTurn, 'ucs-answer-footer');

                    const markdownDoc = summaryDiv ? findInShadows(summaryDiv, '.markdown-document') : null;
                    const text = markdownDoc ? markdownDoc.innerText.trim() : "";

                    if (text.length > 0 && ttft === null) {
                        ttft = (performance.now() - tStart) / 1000;
                    }

                    if (text !== lastText) {
                        lastText = text;
                        lastChangeTime = performance.now();
                    }

                    const footerVisible = footer && footer.offsetWidth > 0;
                    const noChangeElapsed = performance.now() - lastChangeTime;

                    if (text.length > 0 && (footerVisible || noChangeElapsed > 3000)) {
                        clearInterval(check);
                        ttlt = (lastChangeTime - tStart) / 1000;
                        resolve({ ttft, ttlt, text_length: text.length, text });
                    }
                }, pollInterval);
            });
        }
        """
        # Start background polling promise in browser context
        poll_task = asyncio.create_task(page.evaluate(poll_js))
        await asyncio.sleep(0.1) # tiny sleep to ensure event listener binds
        
        # Click the send button natively
        await send_locator.click()
        
        # Wait for resolution of the polling task
        res = await poll_task
        
        # Wait briefly for trace ID
        await asyncio.sleep(1.0)
        page.remove_listener("request", handle_request)
        
        # Save console logs to file
        log_dir = f"{run_dir}/logs"
        os.makedirs(log_dir, exist_ok=True)
        log_path = f"{log_dir}/browser_run_{run_id}.log"
        with open(log_path, "w") as lf:
            lf.write("\n".join(console_logs))
            
        from chart_generator import slugify
        slug = slugify(scenario_name)

        if "error" in res:
            status_code = 500
            err_path = f"{run_dir}/screenshots/{slug}_error_{run_id}.png"
            os.makedirs(os.path.dirname(err_path), exist_ok=True)
            try:
                await page.screenshot(path=err_path, timeout=10000)
            except Exception as e:
                print(f"Warning: Failed to capture error screenshot for run {run_id} ({slug}): {e}")
            await page.close()
            return {
                "status_code": status_code,
                "error": f"{res.get('error')} (Console: {log_path})",
                "ttft": res.get("ttft"),
                "ttlt": res.get("partial_ttlt") or (time.time() - start_time),
                "response_text": "",
                "generation_speed": 0.0,
                "trace_id": trace_id or "N/A"
            }
            
        # Capture success screenshot (safely wrapped to prevent screenshot rendering timeouts from failing the scenario)
        shot_path = f"screenshots/{slug}_run_{run_id}.png"
        abs_shot_path = f"{run_dir}/{shot_path}"
        os.makedirs(os.path.dirname(abs_shot_path), exist_ok=True)
        try:
            await page.screenshot(path=abs_shot_path, timeout=10000)
        except Exception as e:
            print(f"Warning: Failed to capture success screenshot for run {run_id} ({slug}): {e}")
            shot_path = None
        await page.close()
        
        response_text = res.get("text", "")
        generation_duration = (res["ttlt"] - res["ttft"]) if (res["ttft"] is not None and res["ttlt"] is not None) else 0.0
        generation_speed = len(response_text) / generation_duration if generation_duration > 0 else 0.0
        
        return {
            "status_code": 200,
            "ttft": res["ttft"],
            "ttlt": res["ttlt"],
            "trace_id": trace_id or "N/A",
            "response_text": response_text,
            "generation_speed": generation_speed,
            "screenshot_path": shot_path,
            "console_logs_path": f"logs/browser_run_{run_id}.log",
            "error": None
        }
    except Exception as e:
        status_code = 500
        if page:
            try:
                from chart_generator import slugify
                slug = slugify(scenario_name)
                err_path = f"{run_dir}/screenshots/{slug}_error_catch_{run_id}.png"
                os.makedirs(os.path.dirname(err_path), exist_ok=True)
                await page.screenshot(path=err_path, timeout=10000)
                await page.close()
            except Exception:
                pass
        return {
            "status_code": status_code,
            "error": str(e),
            "ttft": None,
            "ttlt": time.time() - start_time,
            "response_text": "",
            "generation_speed": 0.0,
            "trace_id": "N/A"
        }

async def worker(semaphore, context, base_url, client, credentials, project_id, engine_id, scenario, query, run_id, run_dir):
    is_ui = (scenario["api"] == "ui")
    if is_ui:
        target_agent_id = scenario.get("agent_id", "core_assistant")
        if target_agent_id == "core_assistant":
            scenario_url = base_url
        else:
            match = re.search(r"/cid/([^/?#]+)", base_url)
            cid = match.group(1) if match else "c33a03fe-9fbc-4ce7-ad44-85195fbe5625"
            scenario_url = f"https://vertexaisearch.cloud.google.com/home/cid/{cid}/r/agent/{target_agent_id}/session/-?hl=en_US"
            
        async with semaphore:
            res = await run_ui_test(context, scenario_url, query, run_id, run_dir, scenario.get("name", "ui"))
            res["run_id"] = run_id
            res["api"] = "ui (CDP)"
            res["skipping_mode"] = "REQUEST_ASSIST"
            return res
            
    async with semaphore:
        is_stream = (scenario["api"] == "streamAssist")
        if is_stream:
            res = await run_async_stream_test(client, credentials, project_id, engine_id, scenario, query)
        else:
            res = await run_async_sync_test(client, credentials, project_id, engine_id, scenario, query)
            res["ttft"] = None
        
        res["run_id"] = run_id
        res["api"] = scenario["api"]
        res["skipping_mode"] = "REQUEST_ASSIST" if "REQUEST_ASSIST" in str(scenario) else "UNSPECIFIED"
        return res

async def main_async(manifest_path, cdp_url=None):
    print(f"Loading configuration manifest: {manifest_path}")
    with open(manifest_path, "r") as f:
        config = json.load(f)
        
    project_id = config["project_id"]
    engine_id = config["engine_id"]
    query = config["query"]
    iterations = config["iterations"]
    max_concurrency = config.get("max_concurrent_calls", 3)
    scenarios = config["scenarios"]
    test_id = config.get("test_id", "unknown")
    
    # Create execution runs folder
    timestamp = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    run_dir = f"runs/run_{timestamp}_{test_id}"
    os.makedirs(run_dir, exist_ok=True)
    print(f"Initialized local execution folder: {run_dir}")
    
    print("Resolving credentials...")
    credentials = get_credentials()
    
    semaphore = asyncio.Semaphore(max_concurrency)
    
    print("Initializing Playwright browser context...")
    async with async_playwright() as p:
        if cdp_url:
            print(f"Connecting to remote browser over CDP: {cdp_url}")
            browser = await p.chromium.connect_over_cdp(cdp_url)
            context = browser.contexts[0]
            
            # Resolve Base URL from open pages
            base_url = None
            for pg in context.pages:
                if "vertexaisearch.cloud.google.com" in pg.url:
                    url = pg.url
                    match = re.search(r"/cid/([^/?#]+)", url)
                    if match:
                        cid = match.group(1)
                        base_url = f"https://vertexaisearch.cloud.google.com/home/cid/{cid}?hl=en_US"
                        break
            if not base_url:
                print("Active Vertex AI Search tab not found. Opening a new tab to resolve Configuration ID...")
                page = await context.new_page()
                await page.goto("https://console.cloud.google.com/gen-app-builder/")
                
                cid = None
                start_auth_time = time.time()
                # Poll for Configuration ID in the URL for up to 90s (in case login is needed)
                while time.time() - start_auth_time < 90:
                    url = page.url
                    match = re.search(r"/cid/([^/?#]+)", url)
                    if match:
                        cid = match.group(1)
                        break
                    await asyncio.sleep(1)
                    
                if not cid:
                    print("ERROR: Active Vertex AI Search tab not found and could not resolve Configuration ID from redirect.")
                    return
                base_url = f"https://vertexaisearch.cloud.google.com/home/cid/{cid}?hl=en_US"
                print(f"Successfully resolved Configuration ID: {cid}")
        else:
            print("Launching new interactive browser instance...")
            # Launch local Chrome / Chromium headfully
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context()
            page = await context.new_page()
            
            print("Navigating to Google Cloud Console (Gen App Builder)...")
            await page.goto("https://console.cloud.google.com/gen-app-builder/")
            
            print("\n>>> Please complete your sign-in to the Vertex AI Search console in the opened browser window...")
            
            cid = None
            start_auth_time = time.time()
            # Poll for Customer ID in the URL for up to 120s
            while time.time() - start_auth_time < 120:
                url = page.url
                match = re.search(r"/cid/([^/?#]+)", url)
                if match:
                    cid = match.group(1)
                    break
                await asyncio.sleep(1)
                
            if not cid:
                print("ERROR: Authentication timed out or Configuration ID not detected. Exiting.")
                await browser.close()
                return
                
            base_url = f"https://vertexaisearch.cloud.google.com/home/cid/{cid}?hl=en_US"
            print(f"Authentication successful! Detected Configuration ID: {cid}")
            
        print(f"Resolved base agent URL: {base_url}")
        
        total_start_time = time.time()
        async with httpx.AsyncClient(timeout=120.0) as client:
            results = {}
            for s in scenarios:
                s_name = s["name"]
                print(f"Scheduling concurrent runs for scenario: {s_name}...")
                tasks = [
                    worker(semaphore, context, base_url, client, credentials, project_id, engine_id, s, s.get("query", query), i, run_dir)
                    for i in range(1, iterations + 1)
                ]
                scenario_results = await asyncio.gather(*tasks)
                results[s_name] = scenario_results
        total_end_time = time.time()
        total_duration_s = total_end_time - total_start_time
        duration_minutes = total_duration_s / 60.0
        total_queries = len(scenarios) * iterations
        throughput_qpm = total_queries / duration_minutes if duration_minutes > 0 else 0.0
                
    # Build report output structures
    results_json = {
        "timestamp": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "test_id": test_id,
        "manifest_used": manifest_path,
        "concurrency_limit": max_concurrency,
        "total_duration_seconds": total_duration_s,
        "queries_per_minute": throughput_qpm,
        "scenarios": {}
    }
    
    # Populate results_json scenarios structure first
    for s in scenarios:
        s_name = s["name"]
        runs = results[s_name]
        
        ttft_list = []
        ttlt_list = []
        speed_list = []
        success_count = 0
        scenario_runs_data = []
        
        for r in runs:
            scenario_runs_data.append(r)
            if not r.get("error"):
                success_count += 1
                if r.get("ttft") is not None:
                    ttft_list.append(r["ttft"])
                if r.get("ttlt") is not None:
                    ttlt_list.append(r["ttlt"])
                if r.get("generation_speed", 0) > 0:
                    speed_list.append(r["generation_speed"])
                    
        # Compute Stats
        ttft_min, ttft_p50, ttft_p90, ttft_p95, ttft_p99, ttft_max, ttft_avg = get_stats(ttft_list)
        ttlt_min, ttlt_p50, ttlt_p90, ttlt_p95, ttlt_p99, ttlt_max, ttlt_avg = get_stats(ttlt_list)
        speed_min, speed_p50, speed_p90, speed_p95, speed_p99, speed_max, speed_avg = get_stats(speed_list)
        success_rate = (success_count / len(runs)) * 100.0 if runs else 0.0
        
        results_json["scenarios"][s_name] = {
            "complexity_level": s.get("complexity_level", "Unknown"),
            "aggregated_stats": {
                "ttft_min_s": ttft_min,
                "ttft_p50_s": ttft_p50,
                "ttft_p90_s": ttft_p90,
                "ttft_p95_s": ttft_p95,
                "ttft_p99_s": ttft_p99,
                "ttft_max_s": ttft_max,
                "ttft_avg_s": ttft_avg,
                "ttlt_min_s": ttlt_min,
                "ttlt_p50_s": ttlt_p50,
                "ttlt_p90_s": ttlt_p90,
                "ttlt_p95_s": ttlt_p95,
                "ttlt_p99_s": ttlt_p99,
                "ttlt_max_s": ttlt_max,
                "ttlt_avg_s": ttlt_avg,
                "generation_speed_min_chars_sec": speed_min,
                "generation_speed_p50_chars_sec": speed_p50,
                "generation_speed_p90_chars_sec": speed_p90,
                "generation_speed_p95_chars_sec": speed_p95,
                "generation_speed_p99_chars_sec": speed_p99,
                "generation_speed_max_chars_sec": speed_max,
                "generation_speed_chars_per_sec_avg": speed_avg,
                "success_rate_percent": success_rate
            },
            "runs": scenario_runs_data
        }

    # Write consolidated results.json outputs first
    with open(f"{run_dir}/results.json", "w") as jf:
        json.dump(results_json, jf, indent=2)
        
    # Generate Charts from results.json
    try:
        from chart_generator import generate_charts_for_run
        chart_links = generate_charts_for_run(f"{run_dir}/results.json", run_dir)
    except Exception as e:
        print(f"Warning: Failed to generate charts: {e}")
        chart_links = {}

    # Now, build report.md structure
    report_md = f"# Latency Audit Report: Test Run {test_id}\n"
    report_md += f"Executed at: `{results_json['timestamp']}` using manifest: `{manifest_path}`\n\n"
    report_md += f"## ⚙️ Run Execution Metadata\n"
    report_md += f"*   **Concurrency Limit**: `{max_concurrency}` simultaneous workers\n"
    report_md += f"*   **Total Duration**: `{total_duration_s:.1f} seconds` ({duration_minutes:.2f} minutes)\n"
    report_md += f"*   **Average Throughput**: `{throughput_qpm:.2f} queries per minute` (Volume tracking)\n\n"
    
    if "combined" in chart_links:
        report_md += "## 📊 Unified Latency Comparison (TTFT vs. TTLT)\n"
        report_md += f"![Unified Latency Comparison]({chart_links['combined']})\n\n"
        report_md += "---\n\n"
    
    for s in scenarios:
        s_name = s["name"]
        runs = results[s_name]
        complexity = s.get("complexity_level", "Unknown")
        
        report_md += f"## Scenario: {s_name}\n"
        report_md += f"*   **Complexity Profile**: `{complexity}`\n\n"
        report_md += "| Run ID | API Used | status_code | TTFT (s) | TTLT (s) | Speed (char/s) | Trace & Screenshot |\n"
        report_md += "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n"
        
        for r in runs:
            if r.get("error"):
                report_md += f"| {r['run_id']} | {r['api']} | {r['status_code']} | ERROR | ERROR | 0.0 | {r['error'][:40]} |\n"
            else:
                ttft_str = f"{r['ttft']:.3f}" if r.get('ttft') is not None else "N/A"
                ttlt_str = f"{r['ttlt']:.3f}" if r.get('ttlt') is not None else "N/A"
                speed_str = f"{r['generation_speed']:.1f}"
                
                trace_url = f"https://console.cloud.google.com/traces/list?project={project_id}&tid={r['trace_id']}" if r.get('trace_id') and r['trace_id'] != "N/A" else ""
                trace_link = f"[Trace Link]({trace_url})" if trace_url else "N/A"
                
                if r.get("screenshot_path"):
                    trace_link += f" \\| [Screenshot]({r['screenshot_path']})"
                    
                report_md += f"| {r['run_id']} | {r['api']} | {r['status_code']} | {ttft_str} | {ttlt_str} | {speed_str} | {trace_link} |\n"
                
        # Append Stats details
        s_stats = results_json["scenarios"][s_name]["aggregated_stats"]
        runs_data = results_json["scenarios"][s_name]["runs"]
        
        # Get raw stats
        ttft_list = [r["ttft"] for r in runs_data if not r.get("error") and r.get("ttft") is not None]
        ttlt_list = [r["ttlt"] for r in runs_data if not r.get("error") and r.get("ttlt") is not None]
        speed_list = [r["generation_speed"] for r in runs_data if not r.get("error") and r.get("generation_speed", 0) > 0]
        
        ttft_min, ttft_p50, ttft_p90, ttft_p95, ttft_p99, ttft_max, ttft_avg = get_stats(ttft_list)
        ttlt_min, ttlt_p50, ttlt_p90, ttlt_p95, ttlt_p99, ttlt_max, ttlt_avg = get_stats(ttlt_list)
        speed_min, speed_p50, speed_p90, speed_p95, speed_p99, speed_max, speed_avg = get_stats(speed_list)
        
        def fmt(val, unit="s"):
            return f"{val:.3f} {unit}" if val is not None else "N/A"
            
        report_md += f"\n**Statistics for {s_name}:**\n"
        report_md += f"* **Success Rate**: {s_stats['success_rate_percent']:.1f}%\n"
        report_md += f"* **TTFT**: Min = {fmt(ttft_min)}, P50 = {fmt(ttft_p50)}, P90 = {fmt(ttft_p90)}, P95 = {fmt(ttft_p95)}, P99 = {fmt(ttft_p99)}, Max = {fmt(ttft_max)}, Avg = {fmt(ttft_avg)}\n"
        report_md += f"* **TTLT**: Min = {fmt(ttlt_min)}, P50 = {fmt(ttlt_p50)}, P90 = {fmt(ttlt_p90)}, P95 = {fmt(ttlt_p95)}, P99 = {fmt(ttlt_p99)}, Max = {fmt(ttlt_max)}, Avg = {fmt(ttlt_avg)}\n"
        report_md += f"* **Speed**: Min = {fmt(speed_min, 'char/s')}, P50 = {fmt(speed_p50, 'char/s')}, P90 = {fmt(speed_p90, 'char/s')}, P95 = {fmt(speed_p95, 'char/s')}, P99 = {fmt(speed_p99, 'char/s')}, Max = {fmt(speed_max, 'char/s')}, Avg = {fmt(speed_avg, 'char/s')}\n\n"
        
        # Append visual charts if generated
        if s_name in chart_links:
            runs_chart = chart_links[s_name].get("runs_chart")
            hist_chart = chart_links[s_name].get("hist_chart")
            if runs_chart or hist_chart:
                report_md += "### 📈 Latency Visualizations\n\n"
                if runs_chart:
                    report_md += f"**Latency Across Runs (TTFT vs TTLT)**:\n\n![Latency Across Runs]({runs_chart})\n\n"
                if hist_chart:
                    report_md += f"**Latency Bin Distribution**:\n\n![Latency Distribution]({hist_chart})\n\n"

    # Add UI Screenshots stacked at the bottom of the markdown report
    report_md += "## 🖼️ Web App UI Run Screenshots\n\n"
    has_ui = False
    ui_scenario_name = next((name for name in results if "ui" in name.lower()), None)
    if ui_scenario_name:
        for r in results[ui_scenario_name]:
            if r.get("screenshot_path"):
                has_ui = True
                report_md += f"### UI Run {r['run_id']}\n"
                report_md += f"![UI Run {r['run_id']}]({r['screenshot_path']})\n\n"
                
    if not has_ui:
        report_md += "*No UI screenshots captured for this run.*\n"

    with open(f"{run_dir}/report.md", "w") as mf:
        mf.write(report_md)
        
    # Print Markdown output to stdout for the session log
    print("\n=================== BENCHMARK REPORT ===================")
    print(report_md)
    print("========================================================")
    print(f"All runs artifacts written successfully to: {run_dir}")

def main():
    parser = argparse.ArgumentParser(description="Yahoo Gemini Enterprise Latency Auditor")
    parser.add_argument(
        "--manifest",
        default="manifests/manifest_multi_query_template.json",
        help="Path to the JSON configuration manifest"
    )
    parser.add_argument(
        "--cdp-url",
        default=None,
        help="Optional Chrome DevTools Protocol URL (e.g. http://localhost:9222) to reuse existing session"
    )
    args = parser.parse_args()
    asyncio.run(main_async(args.manifest, args.cdp_url))

if __name__ == '__main__':
    main()
