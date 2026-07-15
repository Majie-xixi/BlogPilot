from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import time

from blogpost.browser.cdp import CdpSession
from blogpost.browser.chrome import ChromeController
from blogpost.domain import Article, PublishResult, RunStatus
from blogpost.publishers.diagnostics import save_diagnostic


PUBLISH_URL = "https://blog.51cto.com/blogger/publish"


def build_fill_script(title: str, markdown: str, category: str) -> str:
    title_json = json.dumps(title, ensure_ascii=False)
    body_json = json.dumps(markdown, ensure_ascii=False)
    category_json = json.dumps(category, ensure_ascii=False)
    return f"""(() => {{
const title={title_json}, body={body_json}, category={category_json};
const fire=(el)=>{{el.dispatchEvent(new Event('input',{{bubbles:true}}));el.dispatchEvent(new Event('change',{{bubbles:true}}));}};
const visible=(el)=>el && el.offsetParent!==null;
const byText=(selector,text)=>[...document.querySelectorAll(selector)].find(el=>visible(el)&&el.textContent.trim().includes(text));
const markdownTab=byText('button,a,span,div','Markdown'); if(markdownTab) markdownTab.click();
const titleEl=[...document.querySelectorAll('input,textarea')].find(el=>visible(el)&&((el.placeholder||'').includes('标题')||(el.maxLength>=50&&el.maxLength<=200)));
let bodyEl=[...document.querySelectorAll('textarea')].find(el=>visible(el)&&el!==titleEl);
if(titleEl){{titleEl.focus();titleEl.value=title;fire(titleEl);}}
let bodyOk=false;
if(bodyEl){{bodyEl.focus();bodyEl.value=body;fire(bodyEl);bodyOk=true;}}
if(!bodyOk){{const cm=[...document.querySelectorAll('.CodeMirror')].find(visible);if(cm&&cm.CodeMirror){{cm.CodeMirror.setValue(body);bodyOk=true;}}}}
if(!bodyOk){{const editable=[...document.querySelectorAll('[contenteditable=true]')].find(visible);if(editable){{editable.focus();editable.textContent=body;fire(editable);bodyOk=true;}}}}
let categoryOk=false;
for(const select of document.querySelectorAll('select')){{const option=[...select.options].find(o=>o.text.includes(category)||o.text.includes('AI'));if(option){{select.value=option.value;fire(select);categoryOk=true;break;}}}}
if(!categoryOk){{const label=byText('label,button,span,div',category)||byText('label,button,span,div','AI');if(label){{label.click();categoryOk=true;}}}}
let originalOk=false;
const original=byText('label,button,span,div','原创');if(original){{original.click();originalOk=true;}}
return {{titleOk:!!titleEl,bodyOk,categoryOk,originalOk,dry:false,url:location.href}};
}})()"""


@dataclass(slots=True)
class Cto51Publisher:
    chrome: ChromeController
    diagnostic_dir: Path

    def open_login(self) -> None:
        self.chrome.start("https://blog.51cto.com/login")

    def publish(self, article: Article, category: str, dry_run: bool) -> PublishResult:
        if self.chrome.port is None:
            self.chrome.start(PUBLISH_URL)
        target = self.chrome.open_tab(PUBLISH_URL)
        websocket_url = target.get("webSocketDebuggerUrl")
        if not websocket_url:
            return PublishResult(RunStatus.FAILED, message="无法连接 Chrome 编辑页")
        with CdpSession(websocket_url) as session:
            session.command("Page.enable")
            self._wait_ready(session)
            state = session.evaluate(
                "({url:location.href,login:location.href.includes('login')||!!document.querySelector('input[type=password]'),challenge:/验证码|访问受限|安全验证|Restricted Access/i.test(document.body.innerText)})"
            )
            if state.get("login"):
                return PublishResult(RunStatus.FAILED, message="51CTO 登录已失效，请先打开登录窗口")
            if state.get("challenge"):
                return PublishResult(RunStatus.FAILED, message="51CTO 出现验证码或安全验证，需要人工处理")
            filled = session.evaluate(build_fill_script(article.title, article.markdown, category))
            required = (filled.get("titleOk"), filled.get("bodyOk"), filled.get("categoryOk"), filled.get("originalOk"))
            if not all(required):
                html = session.evaluate("document.documentElement.outerHTML") or ""
                diagnostic = save_diagnostic(self.diagnostic_dir, html)
                return PublishResult(
                    RunStatus.FAILED,
                    message=f"51CTO 页面结构未识别完整，诊断文件：{diagnostic}",
                )
            if dry_run:
                return PublishResult(RunStatus.SKIPPED, message="dry-run 已填充编辑器，未点击发布")
            clicked = session.evaluate(
                """(() => {const b=[...document.querySelectorAll('button')].find(x=>x.offsetParent!==null&&/^(发布|发布文章)$/.test(x.textContent.trim()));if(!b)return false;b.click();return true;})()"""
            )
            if not clicked:
                return PublishResult(RunStatus.FAILED, message="找不到最终发布按钮，已停止")
            time.sleep(3)
            url = session.evaluate("location.href")
            if isinstance(url, str) and "blog.51cto.com/" in url and "publish" not in url:
                return PublishResult(RunStatus.PUBLISHED, url=url, message="发布成功")
            return PublishResult(RunStatus.UNKNOWN, message="已点击发布但结果无法确认，禁止自动重试")

    @staticmethod
    def _wait_ready(session: CdpSession, timeout: float = 15) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if session.evaluate("document.readyState") in ("interactive", "complete"):
                return
            time.sleep(0.2)
        raise TimeoutError("51CTO 编辑页加载超时")
