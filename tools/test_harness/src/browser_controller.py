import asyncio
import re
import time
from playwright.async_api import Page, BrowserContext

class GeminiEnterpriseController:
    def __init__(self, context: BrowserContext, config_id: str):
        self.context = context
        self.cid = config_id
        self.page: Page = None
        self.last_trace_id = None
        
    async def initialize(self):
        """Creates a new page session and registers request/trace interceptors."""
        self.page = await self.context.new_page()
        
        async def intercept_request(req):
            if "assistants/default_assistant:" in req.url:
                headers = await req.all_headers()
                trace_context = headers.get("x-cloud-trace-context", "")
                if trace_context:
                    self.last_trace_id = trace_context.split("/")[0]
                    
        self.page.on("request", intercept_request)
        
    async def goto_core_assistant(self):
        """Navigates directly to the core assistant standalone chat session."""
        url = f"https://vertexaisearch.cloud.google.com/home/cid/{self.cid}?hl=en_US"
        await self.page.goto(url)
        await self.page.wait_for_selector(".ProseMirror", timeout=30000)

    async def goto_sub_agent(self, agent_id: str):
        """Navigates directly to a specific sub-agent standalone chat session."""
        url = f"https://vertexaisearch.cloud.google.com/home/cid/{self.cid}/r/agent/{agent_id}/session/-?hl=en_US"
        await self.page.goto(url)
        await self.page.wait_for_selector(".ProseMirror", timeout=30000)

    async def submit_query(self, query: str):
        """Programmatically types and submits a query into the ProseMirror editor."""
        input_js = """
        async (query) => {
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
            const pm = findInShadows(document, '.ProseMirror');
            if (!pm) return false;
            pm.focus();
            document.execCommand('selectAll', false, null);
            document.execCommand('delete', false, null);
            document.execCommand('insertText', false, query);
            
            await new Promise(resolve => setTimeout(resolve, 500));
            
            const sendBtn = findInShadows(document, 'md-icon-button.send-button');
            if (sendBtn) {
                sendBtn.click();
                return true;
            }
            return false;
        }
        """
        success = await self.page.evaluate(input_js, query)
        if not success:
            raise Exception("Failed to find or input query into the chat area.")

    async def chat_and_measure(self, query: str, timeout_s: float = 90.0) -> dict:
        """Sends a query, polls response, and measures TTFT and TTLT latency."""
        self.last_trace_id = None  # Reset trace ID for new interaction
        start_time = time.time()
        await self.submit_query(query)
        
        ttft = None
        ttlt = None
        
        response_js = """
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
            
            const conv = findInShadows(document, 'ucs-conversation');
            if (!conv) return null;
            
            const summaries = conv.querySelectorAll('ucs-summary');
            if (summaries.length === 0) return null;
            const lastSummary = summaries[summaries.length - 1];
            
            // Check completeness via the screen reader "Response complete" text
            const thoughts = findInShadows(lastSummary.shadowRoot, 'ucs-agent-thoughts');
            let isComplete = false;
            if (thoughts) {
                const srOnly = findInShadows(thoughts.shadowRoot, '.sr-only');
                if (srOnly && srOnly.textContent.trim() === "Response complete") {
                    isComplete = true;
                }
            }
            
            const markdownDoc = findInShadows(lastSummary.shadowRoot, '.markdown-document');
            const text = markdownDoc ? markdownDoc.innerText.trim() : "";
            
            return {
                text: text,
                isGenerating: !isComplete
            };
        }
        """
        
        while time.time() - start_time < timeout_s:
            res = await self.page.evaluate(response_js)
            if res and res["text"]:
                if ttft is None:
                    ttft = time.time() - start_time
                
                if not res["isGenerating"]:
                    ttlt = time.time() - start_time
                    return {
                        "text": res["text"],
                        "ttft": ttft,
                        "ttlt": ttlt,
                        "trace_id": self.last_trace_id,
                        "error": None
                    }
            await asyncio.sleep(0.1)
            
        return {
            "text": "",
            "ttft": None,
            "ttlt": time.time() - start_time,
            "trace_id": self.last_trace_id,
            "error": "Timeout waiting for generation to complete"
        }

    async def close(self):
        if self.page:
            await self.page.close()
