# /// script
# dependencies = [
#   "playwright>=1.40.0",
#   "httpx>=0.25.0",
#   "google-auth>=2.23.0",
#   "requests>=2.31.0",
#   "matplotlib>=3.8.0",
#   "numpy>=1.26.0",
#   "rich>=13.0.0",
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
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.markdown import Markdown

sys.path.append(os.path.dirname(os.path.abspath(__file__)))


def get_credentials():
    credentials, project = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    if not credentials.valid:
        credentials.refresh(Request())
    return credentials


def get_git_root():
    current = os.path.dirname(os.path.abspath(__file__))
    while current != os.path.dirname(current):
        if os.path.exists(os.path.join(current, ".git")):
            return current
        current = os.path.dirname(current)
    return os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../../../"))

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

async def run_async_stream_test(client, credentials, project_id, engine_id, scenario, query_text, quota_project_id=None):
    base_url = "https://discoveryengine.googleapis.com/v1alpha"
    url = f"{base_url}/projects/{project_id}/locations/global/collections/default_collection/engines/{engine_id}/assistants/default_assistant:streamAssist"
    
    user_project = quota_project_id if quota_project_id else project_id
    trace_id = uuid.uuid4().hex
    
    # Generate random 64-bit Span ID for root span correlation
    import random
    span_id_val = random.randint(1, 2**64 - 1)
    span_id_dec = str(span_id_val)
    span_id_hex = format(span_id_val, '016x')
    
    headers = {
        "Authorization": f"Bearer {credentials.token}",
        "Content-Type": "application/json",
        "X-Goog-User-Project": user_project,
        "x-cloud-trace-context": f"{trace_id}/{span_id_dec};o=1",
        "traceparent": f"00-{trace_id}-{span_id_hex}-01"
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
            
    # Resolve and inject model override if specified
    model_used_attr = scenario.get("model_used")
    model_id = scenario.get("model_id")
    if not model_id and model_used_attr:
        if "3.5 Flash" in model_used_attr or "3.5-flash" in model_used_attr.lower():
            model_id = "gemini-3.5-flash"
        elif "3.1 Pro" in model_used_attr or "3.1-pro" in model_used_attr.lower():
            model_id = "gemini-3.1-pro-preview"
        else:
            model_id = model_used_attr
    if model_id:
        payload["generationSpec"] = {
            "modelId": model_id
        }
        
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
                    "trace_id": trace_id,
                    "span_id": span_id_hex
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
            "span_id": span_id_hex,
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
            "trace_id": trace_id,
            "span_id": span_id_hex
        }

async def run_async_sync_test(client, credentials, project_id, engine_id, scenario, query_text, quota_project_id=None):
    base_url = "https://discoveryengine.googleapis.com/v1alpha"
    url = f"{base_url}/projects/{project_id}/locations/global/collections/default_collection/engines/{engine_id}/assistants/default_assistant:assist"
    
    user_project = quota_project_id if quota_project_id else project_id
    trace_id = uuid.uuid4().hex
    
    # Generate random 64-bit Span ID for root span correlation
    import random
    span_id_val = random.randint(1, 2**64 - 1)
    span_id_dec = str(span_id_val)
    span_id_hex = format(span_id_val, '016x')
    
    headers = {
        "Authorization": f"Bearer {credentials.token}",
        "Content-Type": "application/json",
        "X-Goog-User-Project": user_project,
        "x-cloud-trace-context": f"{trace_id}/{span_id_dec};o=1",
        "traceparent": f"00-{trace_id}-{span_id_hex}-01"
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
            
    # Resolve and inject model override if specified
    model_used_attr = scenario.get("model_used")
    model_id = scenario.get("model_id")
    if not model_id and model_used_attr:
        if "3.5 Flash" in model_used_attr or "3.5-flash" in model_used_attr.lower():
            model_id = "gemini-3.5-flash"
        elif "3.1 Pro" in model_used_attr or "3.1-pro" in model_used_attr.lower():
            model_id = "gemini-3.1-pro-preview"
        else:
            model_id = model_used_attr
    if model_id:
        payload["generationSpec"] = {
            "modelId": model_id
        }
        
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
                "trace_id": trace_id,
                "span_id": span_id_hex
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
            "span_id": span_id_hex,
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
            "trace_id": trace_id,
            "span_id": span_id_hex
        }

async def run_ui_test(context, base_url, query_text, run_id, run_dir, scenario_name="ui", model_name=None):
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
            if "discoveryengine" in req.url or "assist" in req.url or "engines/" in req.url:
                try:
                    headers = await req.all_headers()
                    trace_context = headers.get("x-cloud-trace-context", "")
                    if trace_context:
                        trace_id = trace_context.split("/")[0]
                    post_data = req.post_data
                    print(f"[DEBUG] Intercepted UI request URL: {req.url}")
                    if post_data:
                        print(f"[DEBUG] Intercepted UI post data: {post_data}")
                except Exception:
                    pass
        
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

        if model_name:
            print(f"Selecting model '{model_name}' in Web UI...")
            select_model_js = f"""
            async () => {{
                // Find dropdown button by checking for elements containing current model names (Auto, 3.5 Flash, 3.1 Pro, 2.5 Pro)
                // and closest to the chat input container
                const candidates = [];
                const searchRoot = (root) => {{
                    const all = root.querySelectorAll('*');
                    for (const el of all) {{
                        const text = (el.textContent || '').trim();
                        const isClickable = el.tagName === 'BUTTON' || el.getAttribute('role') === 'button' || el.classList.contains('clickable') || el.tagName === 'DIV' || el.tagName === 'SPAN';
                        if (isClickable && (text === 'Auto' || text === '3.5 Flash' || text === '3.1 Pro' || text === '2.5 Pro' || text.includes('Auto ▾') || text.includes('Auto v'))) {{
                            candidates.push(el);
                        }}
                        if (el.shadowRoot) {{
                            searchRoot(el.shadowRoot);
                        }}
                    }}
                }};
                searchRoot(document);
                
                if (candidates.length === 0) {{
                    console.log("No dropdown button candidates found.");
                    return false;
                }}
                
                // Prefer the candidate closest to the ProseMirror input
                const input = document.querySelector('.ProseMirror');
                let dropdown = candidates[0];
                if (input && candidates.length > 1) {{
                    const inputRect = input.getBoundingClientRect();
                    candidates.sort((a, b) => {{
                        const rectA = a.getBoundingClientRect();
                        const rectB = b.getBoundingClientRect();
                        const distA = Math.abs(rectA.top - inputRect.top);
                        const distB = Math.abs(rectB.top - inputRect.top);
                        return distA - distB;
                    }});
                    dropdown = candidates[0];
                }}
                
                dropdown.click();
                await new Promise(r => setTimeout(r, 800)); // wait for overlay to animate
                
                // Find option containing the target model text (strip "Gemini " prefix if present)
                let targetText = "{model_name}";
                if (targetText.startsWith("Gemini ")) {{
                    targetText = targetText.replace("Gemini ", "");
                }}
                
                const findOptionInShadows = (root, checkFn) => {{
                    const all = root.querySelectorAll('*');
                    for (const el of all) {{
                        if (checkFn(el)) return el;
                        if (el.shadowRoot) {{
                            const found = findOptionInShadows(el.shadowRoot, checkFn);
                            if (found) return found;
                        }}
                    }}
                    return null;
                }};
                
                const option = findOptionInShadows(document, (el) => {{
                    const text = (el.textContent || '').trim();
                    const isOption = el.tagName === 'MAT-OPTION' || el.getAttribute('role') === 'option' || el.getAttribute('role') === 'menuitem' || el.classList.contains('mat-option') || el.classList.contains('menu-item') || el.tagName === 'DIV' || el.tagName === 'SPAN';
                    return isOption && text.includes(targetText) && text.length < 100;
                }});
                
                if (!option) {{
                    dropdown.click(); // dismiss
                    console.log("Target option not found: " + targetText);
                    return false;
                }}
                
                option.click();
                await new Promise(r => setTimeout(r, 800)); // wait for model switch processing
                return true;
            }}
            """
            success = await page.evaluate(select_model_js)
            if success:
                print(f"Successfully configured model '{model_name}' in browser session.")
                await asyncio.sleep(2.0) # allow UI state to settle
            else:
                print(f"Warning: Could not select model '{model_name}' in UI. Defaulting to engine standard.")

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
        
        from chart_generator import slugify
        slug = slugify(scenario_name)

        if "error" in res:
            status_code = 500
            log_dir = f"{run_dir}/logs"
            os.makedirs(log_dir, exist_ok=True)
            log_path = f"{log_dir}/{slug}_run_{run_id}.log"
            
            audit_log = []
            audit_log.append("=========================================")
            audit_log.append("BROWSER EXECUTION FAILURE AUDIT LOG")
            audit_log.append("=========================================")
            audit_log.append(f"Timestamp: {datetime.datetime.now(datetime.timezone.utc).isoformat()}")
            audit_log.append(f"Scenario:  {scenario_name}")
            audit_log.append(f"Run ID:    {run_id}")
            audit_log.append(f"Model:     {model_name or 'Auto'}")
            audit_log.append(f"Status:    500 Internal Error")
            audit_log.append(f"Error:     {res.get('error')}")
            audit_log.append(f"TTFT:      {res.get('ttft') or 'N/A'}")
            audit_log.append(f"TTLT:      {res.get('partial_ttlt') or (time.time() - start_time):.3f} s (partial)")
            audit_log.append("")
            audit_log.append("=========================================")
            audit_log.append("BROWSER CONSOLE LOGS")
            audit_log.append("=========================================")
            if console_logs:
                audit_log.extend(console_logs)
            else:
                audit_log.append("(No console messages captured)")
                
            try:
                with open(log_path, "w") as lf:
                    lf.write("\n".join(audit_log))
                err_msg = f"{res.get('error')} (Console: {log_path})"
            except Exception as le:
                print(f"Warning: Failed to write failure audit log: {le}")
                err_msg = res.get('error')
                
            err_path = f"{run_dir}/screenshots/{slug}_error_{run_id}.png"
            os.makedirs(os.path.dirname(err_path), exist_ok=True)
            try:
                await page.screenshot(path=err_path, timeout=10000)
            except Exception as e:
                print(f"Warning: Failed to capture error screenshot for run {run_id} ({slug}): {e}")
            await page.close()
            return {
                "status_code": status_code,
                "error": err_msg,
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
        
        # Save structured success audit log to file
        log_dir = f"{run_dir}/logs"
        os.makedirs(log_dir, exist_ok=True)
        log_path = f"{log_dir}/{slug}_run_{run_id}.log"
        
        audit_log = []
        audit_log.append("=========================================")
        audit_log.append("BROWSER EXECUTION SUCCESS AUDIT LOG")
        audit_log.append("=========================================")
        audit_log.append(f"Timestamp: {datetime.datetime.now(datetime.timezone.utc).isoformat()}")
        audit_log.append(f"Scenario:  {scenario_name}")
        audit_log.append(f"Run ID:    {run_id}")
        audit_log.append(f"Model:     {model_name or 'Auto'}")
        audit_log.append(f"Status:    200 OK")
        audit_log.append(f"TTFT:      {res['ttft']:.3f} s" if res.get('ttft') is not None else "TTFT:      N/A")
        audit_log.append(f"TTLT:      {res['ttlt']:.3f} s")
        audit_log.append(f"Speed:     {generation_speed:.1f} char/s")
        audit_log.append("")
        audit_log.append("Response Snippet:")
        audit_log.append("-----------------------------------------")
        audit_log.append(response_text[:300] + ("..." if len(response_text) > 300 else ""))
        audit_log.append("-----------------------------------------")
        audit_log.append("")
        audit_log.append("=========================================")
        audit_log.append("BROWSER CONSOLE LOGS")
        audit_log.append("=========================================")
        if console_logs:
            audit_log.extend(console_logs)
        else:
            audit_log.append("(No console messages captured)")
            
        try:
            with open(log_path, "w") as lf:
                lf.write("\n".join(audit_log))
        except Exception as le:
            print(f"Warning: Failed to write success audit log: {le}")
            
        return {
            "status_code": 200,
            "ttft": res["ttft"],
            "ttlt": res["ttlt"],
            "trace_id": trace_id or "N/A",
            "response_text": response_text,
            "generation_speed": generation_speed,
            "screenshot_path": shot_path,
            "console_logs_path": f"logs/{slug}_run_{run_id}.log",
            "error": None
        }
    except Exception as e:
        status_code = 500
        # Save structured exception audit log to file
        try:
            log_dir = f"{run_dir}/logs"
            os.makedirs(log_dir, exist_ok=True)
            log_path = f"{log_dir}/{slug}_run_{run_id}.log"
            
            audit_log = []
            audit_log.append("=========================================")
            audit_log.append("BROWSER EXECUTION EXCEPTION AUDIT LOG")
            audit_log.append("=========================================")
            audit_log.append(f"Timestamp: {datetime.datetime.now(datetime.timezone.utc).isoformat()}")
            audit_log.append(f"Scenario:  {scenario_name}")
            audit_log.append(f"Run ID:    {run_id}")
            audit_log.append(f"Model:     {model_name or 'Auto'}")
            audit_log.append(f"Status:    500 Internal Error")
            audit_log.append(f"Exception: {str(e)}")
            audit_log.append(f"TTLT:      {time.time() - start_time:.3f} s (elapsed)")
            audit_log.append("")
            audit_log.append("=========================================")
            audit_log.append("BROWSER CONSOLE LOGS")
            audit_log.append("=========================================")
            if console_logs:
                audit_log.extend(console_logs)
            else:
                audit_log.append("(No console messages captured)")
                
            with open(log_path, "w") as lf:
                lf.write("\n".join(audit_log))
            error_msg = f"{str(e)} (Console: {log_path})"
        except Exception as le:
            print(f"Warning: Failed to write exception audit log: {le}")
            error_msg = str(e)
            
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
            "error": error_msg,
            "ttft": None,
            "ttlt": time.time() - start_time,
            "response_text": "",
            "generation_speed": 0.0,
            "trace_id": "N/A"
        }

async def worker(semaphore, context, base_url, client, credentials, project_id, engine_id, scenario, query, run_id, run_dir, quota_project_id=None):
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
            res = await run_ui_test(context, scenario_url, query, run_id, run_dir, scenario.get("name", "ui"), scenario.get("model_used"))
            res["run_id"] = run_id
            res["api"] = "ui (CDP)"
            res["skipping_mode"] = "REQUEST_ASSIST"
            return res
            
    async with semaphore:
        is_stream = (scenario["api"] == "streamAssist")
        if is_stream:
            res = await run_async_stream_test(client, credentials, project_id, engine_id, scenario, query, quota_project_id)
        else:
            res = await run_async_sync_test(client, credentials, project_id, engine_id, scenario, query, quota_project_id)
            res["ttft"] = None
        
        res["run_id"] = run_id
        res["api"] = scenario["api"]
        res["skipping_mode"] = "REQUEST_ASSIST" if "REQUEST_ASSIST" in str(scenario) else "UNSPECIFIED"
        return res

def get_scenario_base_name(name):
    base = name
    for suffix in [" (Stream)", " (UI)", " (Stream API)", " (UI Preview)"]:
        if base.endswith(suffix):
            base = base[:-len(suffix)]
    if " - Gemini " in base:
        base = base.split(" - Gemini ")[0]
    return base

async def main_async(manifest_path, cdp_url=None):
    print(f"Loading configuration manifest: {manifest_path}")
    with open(manifest_path, "r") as f:
        config = json.load(f)
        
    project_id = config["project_id"]
    quota_project_id = config.get("quota_project_id")
    engine_id = config["engine_id"]
    query = config["query"]
    iterations = config["iterations"]
    max_concurrency = config.get("max_concurrent_calls", 3)
    scenarios = config["scenarios"]
    test_id = config.get("test_id", "unknown")
    model_used = config.get("model_used", "Gemini 3.5 Flash")
    
    # Create execution runs folder
    timestamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d_%H%M%S")
    run_dir = f"runs/run_{timestamp}_{test_id}"
    os.makedirs(run_dir, exist_ok=True)
    print(f"Initialized local execution folder: {run_dir}")
    
    # Archive the manifest configuration file into the run output folder for provenance
    import shutil
    git_root = get_git_root()
    copied_manifest_filename = f"manifest_{timestamp}.json"
    copied_manifest_path = os.path.join(run_dir, copied_manifest_filename)
    shutil.copy2(manifest_path, copied_manifest_path)
    copied_manifest_abs = os.path.abspath(copied_manifest_path)
    copied_manifest_git_rel = os.path.relpath(copied_manifest_abs, git_root)
    print(f"Archived configuration manifest for provenance: {copied_manifest_git_rel}")
    
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
                dashboard_url = f"https://console.cloud.google.com/gemini-enterprise/locations/global/engines/{engine_id}/overview/dashboard?project={project_id}"
                print(f"Navigating to Gemini Enterprise Dashboard: {dashboard_url}")
                await page.goto(dashboard_url)
                
                cid = None
                start_auth_time = time.time()
                resolve_cid_js = """
                () => {
                    const findLinkInShadows = (root) => {
                        const link = root.querySelector('a[href*="vertexaisearch.cloud.google.com/home/cid/"]');
                        if (link) return link.href;
                        const all = root.querySelectorAll('*');
                        for (const el of all) {
                            if (el.shadowRoot) {
                                const found = findLinkInShadows(el.shadowRoot);
                                if (found) return found;
                            }
                        }
                        return null;
                    };
                    return findLinkInShadows(document);
                }
                """
                # Poll for Configuration ID in the DOM for up to 90s (in case login/redirects are needed)
                while time.time() - start_auth_time < 90:
                    try:
                        href = await page.evaluate(resolve_cid_js)
                        if href:
                            match = re.search(r"/cid/([^/?#]+)", href)
                            if match:
                                cid = match.group(1)
                                break
                    except Exception:
                        pass
                    await asyncio.sleep(1)
                    
                if not cid:
                    print("ERROR: Could not resolve Configuration ID from the Gemini Enterprise Dashboard. Exiting.")
                    return
                base_url = f"https://vertexaisearch.cloud.google.com/home/cid/{cid}?hl=en_US"
                print(f"Successfully resolved Configuration ID: {cid}")
        else:
            print("Launching new interactive browser instance...")
            # Launch local Chrome / Chromium headfully
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context()
            page = await context.new_page()
            
            dashboard_url = f"https://console.cloud.google.com/gemini-enterprise/locations/global/engines/{engine_id}/overview/dashboard?project={project_id}"
            print(f"Navigating to Gemini Enterprise Dashboard: {dashboard_url}")
            await page.goto(dashboard_url)
            
            print("\n>>> Please complete your sign-in to the console in the opened browser window...")
            
            cid = None
            start_auth_time = time.time()
            resolve_cid_js = """
            () => {
                const findLinkInShadows = (root) => {
                    const link = root.querySelector('a[href*="vertexaisearch.cloud.google.com/home/cid/"]');
                    if (link) return link.href;
                    const all = root.querySelectorAll('*');
                    for (const el of all) {
                        if (el.shadowRoot) {
                            const found = findLinkInShadows(el.shadowRoot);
                            if (found) return found;
                        }
                    }
                    return null;
                };
                return findLinkInShadows(document);
            }
            """
            # Poll for Customer ID in the DOM for up to 120s
            while time.time() - start_auth_time < 120:
                try:
                    href = await page.evaluate(resolve_cid_js)
                    if href:
                        match = re.search(r"/cid/([^/?#]+)", href)
                        if match:
                            cid = match.group(1)
                            break
                except Exception:
                    pass
                await asyncio.sleep(1)
                
            if not cid:
                print("ERROR: Authentication timed out or Configuration ID not detected. Exiting.")
                await browser.close()
                return
                
            base_url = f"https://vertexaisearch.cloud.google.com/home/cid/{cid}?hl=en_US"
            print(f"Authentication successful! Detected Configuration ID: {cid}")
            
        print(f"Resolved base agent URL: {base_url}")
        
        console = Console()
        console.print()
        console.print(Panel(
            Text("🚀 LAUNCHING LATENCY BENCHMARKING TESTING ENGINE\n"
                 "Running streamAssist REST API & Web App UI Scenario Testing...",
                 style="bold white", justify="center"),
            style="bold cyan",
            border_style="cyan",
            title="[bold yellow]BENCHMARKING RUNNING[/bold yellow]",
            title_align="center"
        ))
        console.print()
        
        total_start_time = time.time()
        async with httpx.AsyncClient(timeout=120.0) as client:
            results = {}
            for s in scenarios:
                s_name = s["name"]
                print(f"Scheduling concurrent runs for scenario: {s_name}...")
                tasks = [
                    worker(semaphore, context, base_url, client, credentials, project_id, engine_id, s, s.get("query", query), i, run_dir, quota_project_id)
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
        "timestamp": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "test_id": test_id,
        "model_used": model_used,
        "manifest_used": copied_manifest_git_rel,
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

    # Now, build report.md structure using templates
    git_root = get_git_root()
    if test_id == "verify":
        report_title = "GE Benchmarking Testing Report: Verification Run"
    else:
        report_title = f"GE Benchmarking Testing Report: Run {test_id}"
        
    # Read templates
    config_dir = os.path.join(git_root, "tools/test_harness/config")
    try:
        with open(os.path.join(config_dir, "report_template.md"), "r") as f:
            report_template = f.read()
        with open(os.path.join(config_dir, "scenario_template.md"), "r") as f:
            scenario_template = f.read()
        with open(os.path.join(config_dir, "screenshot_template.md"), "r") as f:
            screenshot_template = f.read()
    except Exception as e:
        print(f"Error loading report templates from {config_dir}: {e}")
        raise e

    readme_abs = os.path.abspath(os.path.join(git_root, "tools/test_harness/README.md"))
    readme_rel = os.path.relpath(readme_abs, run_dir)

    # Calculate High-Level Averages
    api_ttfts = []
    api_ttlts = []
    ui_ttfts = []
    ui_ttlts = []
    for s_name, runs in results.items():
        for r in runs:
            if r.get("error"):
                continue
            if "ui" in r["api"].lower():
                if r.get("ttft") is not None:
                    ui_ttfts.append(r["ttft"])
                if r.get("ttlt") is not None:
                    ui_ttlts.append(r["ttlt"])
            else:
                if r.get("ttft") is not None:
                    api_ttfts.append(r["ttft"])
                if r.get("ttlt") is not None:
                    api_ttlts.append(r["ttlt"])
                    
    avg_api_ttft_val = sum(api_ttfts) / len(api_ttfts) if api_ttfts else None
    avg_api_ttlt_val = sum(api_ttlts) / len(api_ttlts) if api_ttlts else None
    avg_ui_ttft_val = sum(ui_ttfts) / len(ui_ttfts) if ui_ttfts else None
    avg_ui_ttlt_val = sum(ui_ttlts) / len(ui_ttlts) if ui_ttlts else None

    def fmt_avg(val):
        return f"`{val:.3f} s`" if val is not None else "`N/A`"

    # Group scenarios by their base name (combining models and pathways)
    from collections import defaultdict
    grouped = defaultdict(list)
    for s in scenarios:
        base_name = get_scenario_base_name(s["name"])
        grouped[base_name].append(s)

    # Helper to detect connectors
    def detect_connectors(scenario_name):
        connectors = []
        name_upper = scenario_name.upper()
        if "GDRIVE" in name_upper or "GOOGLE DRIVE" in name_upper or "HR EMPLOYEE HANDBOOK" in name_upper:
            connectors.append("Google Drive")
        if "CONFLUENCE" in name_upper:
            connectors.append("Confluence")
        if "JIRA" in name_upper:
            connectors.append("Jira")
        if "LUMAPPS" in name_upper or "GCS" in name_upper:
            connectors.append("LumApps (GCS)")
        if "3-WAY" in name_upper:
            connectors.extend(["LumApps (GCS)", "Confluence", "Jira"])
        if not connectors:
            connectors.append("Default Search Index")
        return list(set(connectors))

    scenarios_section = ""
    for base_name, group in grouped.items():
        first_s = group[0]
        s_query = first_s.get("query", query)
        complexity = first_s.get("complexity_level", "Unknown")
        expected_connectors = detect_connectors(base_name)
        
        flash_api = next((s for s in group if "3.5 flash" in s["name"].lower() and "ui" not in s["api"].lower()), None)
        flash_ui = next((s for s in group if "3.5 flash" in s["name"].lower() and "ui" in s["api"].lower()), None)
        pro_api = next((s for s in group if "3.1 pro" in s["name"].lower() and "ui" not in s["api"].lower()), None)
        pro_ui = next((s for s in group if "3.1 pro" in s["name"].lower() and "ui" in s["api"].lower()), None)
        
        def get_model_stats(s_dict):
            if not s_dict:
                return "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A"
            s_name = s_dict["name"]
            runs_data = results_json["scenarios"][s_name]["runs"]
            ttft_list = [r["ttft"] for r in runs_data if not r.get("error") and r.get("ttft") is not None]
            ttlt_list = [r["ttlt"] for r in runs_data if not r.get("error") and r.get("ttlt") is not None]
            ttft_min, ttft_p50, _, ttft_p95, _, ttft_max, _ = get_stats(ttft_list)
            ttlt_min, ttlt_p50, _, ttlt_p95, _, ttlt_max, _ = get_stats(ttlt_list)
            
            def fmt_val(val):
                return f"{val:.3f} s" if val is not None else "N/A"
            return fmt_val(ttft_min), fmt_val(ttft_p50), fmt_val(ttft_p95), fmt_val(ttft_max), fmt_val(ttlt_min), fmt_val(ttlt_p50), fmt_val(ttlt_p95), fmt_val(ttlt_max)

        f_api_ttft_min, f_api_ttft_p50, f_api_ttft_p95, f_api_ttft_max, f_api_ttlt_min, f_api_ttlt_p50, f_api_ttlt_p95, f_api_ttlt_max = get_model_stats(flash_api)
        f_ui_ttft_min, f_ui_ttft_p50, f_ui_ttft_p95, f_ui_ttft_max, f_ui_ttlt_min, f_ui_ttlt_p50, f_ui_ttlt_p95, f_ui_ttlt_max = get_model_stats(flash_ui)
        p_api_ttft_min, p_api_ttft_p50, p_api_ttft_p95, p_api_ttft_max, p_api_ttlt_min, p_api_ttlt_p50, p_api_ttlt_p95, p_api_ttlt_max = get_model_stats(pro_api)
        p_ui_ttft_min, p_ui_ttft_p50, p_ui_ttft_p95, p_ui_ttft_max, p_ui_ttlt_min, p_ui_ttlt_p50, p_ui_ttlt_p95, p_ui_ttlt_max = get_model_stats(pro_ui)
        
        # Build Detailed Invocations Rows
        run_rows = ""
        for i in range(1, iterations + 1):
            def get_run_row(s_dict, model_name, pathway_name, run_idx, is_first_row_for_run=False):
                run_cell = f"**{run_idx}**" if is_first_row_for_run else ""
                if not s_dict:
                    return ""
                s_name = s_dict["name"]
                runs_data = results_json["scenarios"][s_name]["runs"]
                run_data = next((r for r in runs_data if r["run_id"] == run_idx), None)
                if not run_data:
                    return ""
                
                if run_data.get("error"):
                    err_msg = run_data["error"].replace("\n", " ")[:60]
                    return f"| {run_cell} | {model_name} | {pathway_name} | {run_data['status_code']} | ERROR | ERROR | 0.0 | {err_msg} | N/A |\n"
                
                ttft_str = f"{run_data['ttft']:.3f}" if run_data.get('ttft') is not None else "N/A"
                ttlt_str = f"{run_data['ttlt']:.3f}" if run_data.get('ttlt') is not None else "N/A"
                speed_str = f"{run_data['generation_speed']:.1f}"
                
                if "ui" in s_dict["api"].lower():
                    screenshot_link = f"[Screenshot]({run_data['screenshot_path']})" if run_data.get('screenshot_path') else "N/A"
                    return f"| {run_cell} | {model_name} | UI (Preview) | {run_data['status_code']} | {ttft_str} | {ttlt_str} | {speed_str} | {screenshot_link} | N/A |\n"
                else:
                    trace_id_str = f"`{run_data['trace_id']}`" if run_data.get('trace_id') and run_data['trace_id'] != "N/A" else "N/A"
                    span_id_str = f"`{run_data['span_id']}`" if run_data.get('span_id') and run_data['span_id'] != "N/A" else "N/A"
                    return f"| {run_cell} | {model_name} | API (Stream) | {run_data['status_code']} | {ttft_str} | {ttlt_str} | {speed_str} | {trace_id_str} | {span_id_str} |\n"

            run_rows += get_run_row(flash_api, "Gemini 3.5 Flash", "API (Stream)", i, is_first_row_for_run=True)
            run_rows += get_run_row(flash_ui, "Gemini 3.5 Flash", "UI (Preview)", i, is_first_row_for_run=False)
            run_rows += get_run_row(pro_api, "Gemini 3.1 Pro", "API (Stream)", i, is_first_row_for_run=False)
            run_rows += get_run_row(pro_ui, "Gemini 3.1 Pro", "UI (Preview)", i, is_first_row_for_run=False)

        # Format scenario template
        scenario_md = scenario_template.format(
            scenario_name=base_name,
            complexity_level=f"`{complexity}` (Expected Connectors: {', '.join(expected_connectors)})",
            project_id=project_id,
            f_api_ttft_min=f_api_ttft_min, f_api_ttft_p50=f_api_ttft_p50, f_api_ttft_p95=f_api_ttft_p95, f_api_ttft_max=f_api_ttft_max,
            f_api_ttlt_min=f_api_ttlt_min, f_api_ttlt_p50=f_api_ttlt_p50, f_api_ttlt_p95=f_api_ttlt_p95, f_api_ttlt_max=f_api_ttlt_max,
            f_ui_ttft_min=f_ui_ttft_min, f_ui_ttft_p50=f_ui_ttft_p50, f_ui_ttft_p95=f_ui_ttft_p95, f_ui_ttft_max=f_ui_ttft_max,
            f_ui_ttlt_min=f_ui_ttlt_min, f_ui_ttlt_p50=f_ui_ttlt_p50, f_ui_ttlt_p95=f_ui_ttlt_p95, f_ui_ttlt_max=f_ui_ttlt_max,
            p_api_ttft_min=p_api_ttft_min, p_api_ttft_p50=p_api_ttft_p50, p_api_ttft_p95=p_api_ttft_p95, p_api_ttft_max=p_api_ttft_max,
            p_api_ttlt_min=p_api_ttlt_min, p_api_ttlt_p50=p_api_ttlt_p50, p_api_ttlt_p95=p_api_ttlt_p95, p_api_ttlt_max=p_api_ttlt_max,
            p_ui_ttft_min=p_ui_ttft_min, p_ui_ttft_p50=p_ui_ttft_p50, p_ui_ttft_p95=p_ui_ttft_p95, p_ui_ttft_max=p_ui_ttft_max,
            p_ui_ttlt_min=p_ui_ttlt_min, p_ui_ttlt_p50=p_ui_ttlt_p50, p_ui_ttlt_p95=p_ui_ttlt_p95, p_ui_ttlt_max=p_ui_ttlt_max,
            run_rows=run_rows
        )
        scenarios_section += scenario_md

    # Build Screenshots Section
    screenshots_section = "## 🖼️ Web App UI Run Screenshots\n\n"
    has_ui = False
    for s_name, runs in results.items():
        if "ui" in s_name.lower():
            for r in runs:
                if r.get("screenshot_path"):
                    has_ui = True
                    screenshot_abs = os.path.abspath(os.path.join(run_dir, r['screenshot_path']))
                    screenshot_git_rel = os.path.relpath(screenshot_abs, git_root)
                    screenshots_section += screenshot_template.format(
                        run_id=r['run_id'],
                        scenario_name=s_name,
                        screenshot_path=r['screenshot_path'],
                        screenshot_path_git_rel=screenshot_git_rel
                    )
    if not has_ui:
        screenshots_section += "*No UI screenshots captured for this run.\n\n"

    chart_path = chart_links.get('combined', '')
    
    # Format the master report
    final_report = report_template.format(
        report_title=report_title,
        timestamp=results_json['timestamp'],
        model_used=model_used,
        manifest_rel=copied_manifest_git_rel,
        readme_rel=readme_rel,
        run_dir=run_dir,
        manifest_filename=copied_manifest_filename,
        avg_api_ttft=fmt_avg(avg_api_ttft_val),
        avg_api_ttlt=fmt_avg(avg_api_ttlt_val),
        avg_ui_ttft=fmt_avg(avg_ui_ttft_val),
        avg_ui_ttlt=fmt_avg(avg_ui_ttlt_val),
        chart_path=chart_path,
        scenarios_section=scenarios_section,
        screenshots_section=screenshots_section,
        max_concurrency=max_concurrency,
        total_duration_s=total_duration_s,
        duration_minutes=duration_minutes,
        throughput_qpm=throughput_qpm
    )

    with open(f"{run_dir}/report.md", "w") as mf:
        mf.write(final_report)


    # Print a beautiful, concise summary with a git-relative hyperlink to the report.md file
    report_abs = os.path.abspath(os.path.join(run_dir, "report.md"))
    report_git_rel = os.path.relpath(report_abs, git_root)
    
    console = Console()
    console.print()
    
    summary_text = (
        f"[bold green]✔ All benchmarking scenarios executed successfully![/bold green]\n\n"
        f"[bold white]Benchmarking Report:[/bold white]\n"
        f"  [bold cyan]{report_git_rel}[/bold cyan]"
    )
    
    console.print(Panel(
        summary_text,
        style="bold green",
        border_style="green",
        title="[bold yellow]BENCHMARK COMPLETE[/bold yellow]",
        title_align="center",
        padding=(1, 2)
    ))
    console.print()

def main():
    parser = argparse.ArgumentParser(description="Yahoo Gemini Enterprise Latency Benchmarking Testing Tool")
    parser.add_argument(
        "--manifest",
        default="config/manifest_multi_query_template.json",
        help="Path to the JSON configuration manifest"
    )
    parser.add_argument(
        "--cdp",
        "--cdp-url",
        dest="cdp_url",
        default=None,
        help="Optional Chrome DevTools Protocol URL (e.g. http://localhost:9223) to reuse existing session"
    )
    args = parser.parse_args()
    asyncio.run(main_async(args.manifest, args.cdp_url))

if __name__ == '__main__':
    main()
