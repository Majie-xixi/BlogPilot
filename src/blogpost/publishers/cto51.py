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


def build_fill_script(title: str, markdown: str, category: str = "") -> str:
    """Build a Vue/React-safe editor fill script.

    The native value setter is important: assigning ``element.value`` directly
    can be overwritten when the 51CTO editor finishes hydrating.
    """
    title_json = json.dumps(title, ensure_ascii=False)
    body_json = json.dumps(markdown, ensure_ascii=False)
    category_json = json.dumps(category, ensure_ascii=False)
    return f"""(() => {{
const title={title_json}, body={body_json}, category={category_json};
const visible=(el)=>!!el && el.offsetParent!==null;
const fire=(el)=>{{el.dispatchEvent(new Event('input',{{bubbles:true}}));el.dispatchEvent(new Event('change',{{bubbles:true}}));}};
const setNative=(el,value)=>{{
  const proto=el instanceof HTMLTextAreaElement?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;
  const setter=Object.getOwnPropertyDescriptor(proto,'value')?.set;
  if(setter) setter.call(el,value); else el.value=value;
  fire(el);
}};
const titleEl=document.querySelector('input.title_input')||[...document.querySelectorAll('input')].find(el=>visible(el)&&(el.placeholder||'').includes('请输入标题'));
const bodyEl=document.querySelector('textarea.write-area')||[...document.querySelectorAll('textarea')].find(el=>visible(el)&&(el.placeholder||'').includes('请输入正文'));
if(titleEl){{titleEl.focus();setNative(titleEl,title);titleEl.blur();}}
if(bodyEl){{bodyEl.focus();setNative(bodyEl,body);bodyEl.blur();}}
return {{titleFound:!!titleEl,bodyFound:!!bodyEl,titleOk:titleEl?.value===title,bodyOk:bodyEl?.value===body,url:location.href}};
}})()"""


OPEN_SETTINGS_SCRIPT = """(() => {
const visible=(el)=>!!el&&el.offsetParent!==null;
const button=document.querySelector('button.edit-submit')||[...document.querySelectorAll('button')].find(el=>visible(el)&&el.textContent.trim()==='发布文章');
if(!button)return false;
button.click();
return true;
})()"""


def build_settings_script(category: str) -> str:
    category_json = json.dumps(category, ensure_ascii=False)
    return f"""(() => {{
const category={category_json};
const visible=(el)=>!!el&&el.offsetParent!==null;
const exact=(text)=>[...document.querySelectorAll('label,button,li,span,div')]
  .filter(el=>visible(el)&&el.textContent.trim()===text)
  .sort((a,b)=>a.childElementCount-b.childElementCount)[0];
let categoryOk=false;
const categoryNode=exact(category);
if(categoryNode){{categoryNode.click();categoryOk=true;}}
const typeInput=[...document.querySelectorAll('input')].find(el=>visible(el)&&(el.placeholder||'').includes('文章类型'));
let originalOk=!!typeInput && (typeInput.value||'').includes('原创');
if(typeInput&&!originalOk){{
  typeInput.click();
  const original=exact('原创');
  if(original){{original.click();originalOk=true;}}
}}
const release=[...document.querySelectorAll('button.release')].find(visible);
return {{categoryOk,originalOk,releaseReady:!!release,typeValue:typeInput?.value||'',url:location.href}};
}})()"""


@dataclass(slots=True)
class Cto51Publisher:
    chrome: ChromeController
    diagnostic_dir: Path

    def open_login(self) -> None:
        self.chrome.start("https://blog.51cto.com/login")

    def publish(self, article: Article, category: str, dry_run: bool) -> PublishResult:
        try:
            if self.chrome.port is None:
                # start() already opens the URL; reuse it instead of creating a duplicate tab.
                self.chrome.start(PUBLISH_URL)
                target = self.chrome.wait_for_target(PUBLISH_URL)
            else:
                target = self.chrome.open_tab(PUBLISH_URL)
            websocket_url = target.get("webSocketDebuggerUrl")
            if not websocket_url:
                return PublishResult(RunStatus.FAILED, message="无法连接 Chrome 编辑页面")

            with CdpSession(websocket_url) as session:
                session.command("Page.enable")
                self._wait_editor_stable(session)
                state = session.evaluate(
                    "({url:location.href,login:location.href.includes('login')||!!document.querySelector('input[type=password]'),challenge:/验证码|访问受限|安全验证|Restricted Access/i.test(document.body.innerText)})"
                )
                if state.get("login"):
                    return PublishResult(RunStatus.FAILED, message="51CTO 登录已失效，请先打开登录窗口")
                if state.get("challenge"):
                    return PublishResult(RunStatus.FAILED, message="51CTO 出现验证码或安全验证，需要人工处理")

                filled = self._fill_and_verify(session, article)
                if not (filled.get("titleOk") and filled.get("bodyOk")):
                    return self._diagnostic_failure(session, "51CTO 标题或正文填写后被页面重置")

                if not session.evaluate(OPEN_SETTINGS_SCRIPT):
                    return self._diagnostic_failure(session, "找不到“发布文章”设置按钮")
                self._wait_publish_dialog(session)
                settings = session.evaluate(build_settings_script(category)) or {}
                if not all((settings.get("categoryOk"), settings.get("originalOk"), settings.get("releaseReady"))):
                    return self._diagnostic_failure(session, "51CTO 发布设置未识别完整")

                if dry_run:
                    return PublishResult(
                        RunStatus.SKIPPED,
                        message="安全试运行已填写文章并打开发布设置，未点击最终发布",
                    )

                clicked = session.evaluate(
                    "(() => {const b=[...document.querySelectorAll('button.release')].find(x=>x.offsetParent!==null&&x.textContent.trim()==='发布');if(!b)return false;b.click();return true;})()"
                )
                if not clicked:
                    return PublishResult(RunStatus.FAILED, message="找不到最终发布按钮，已停止")
                return self._wait_publish_result(session)
        except TimeoutError as exc:
            return PublishResult(RunStatus.FAILED, message=str(exc))
        except Exception as exc:
            return PublishResult(RunStatus.FAILED, message=f"51CTO 发布失败：{exc}")

    @staticmethod
    def _wait_editor_stable(session: CdpSession, timeout: float = 20) -> None:
        deadline = time.monotonic() + timeout
        stable = 0
        previous = None
        while time.monotonic() < deadline:
            state = session.evaluate(
                "({url:location.href,ready:document.readyState,title:!!document.querySelector('input.title_input'),body:!!document.querySelector('textarea.write-area'),button:!!document.querySelector('button.edit-submit'),text:(document.body?.innerText||'').length})"
            ) or {}
            if state.get("title") and state.get("body") and state.get("button"):
                signature = (state.get("url"), state.get("text"))
                stable = stable + 1 if signature == previous else 1
                previous = signature
                if stable >= 3:
                    return
            else:
                stable = 0
                previous = None
            time.sleep(0.25)
        url = session.evaluate("location.href") or "未知页面"
        raise TimeoutError(f"51CTO 编辑器加载超时：{url}")

    @staticmethod
    def _fill_and_verify(session: CdpSession, article: Article) -> dict:
        result: dict = {}
        for _ in range(2):
            result = session.evaluate(build_fill_script(article.title, article.markdown)) or {}
            time.sleep(0.6)
            verified = session.evaluate(
                f"({{titleOk:document.querySelector('input.title_input')?.value==={json.dumps(article.title, ensure_ascii=False)},bodyOk:document.querySelector('textarea.write-area')?.value==={json.dumps(article.markdown, ensure_ascii=False)}}})"
            ) or {}
            result.update(verified)
            if result.get("titleOk") and result.get("bodyOk"):
                return result
        return result

    @staticmethod
    def _wait_publish_dialog(session: CdpSession, timeout: float = 8) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if session.evaluate("!![...document.querySelectorAll('button.release')].find(el=>el.offsetParent!==null)"):
                return
            time.sleep(0.2)
        raise TimeoutError("51CTO 发布设置窗口打开超时")

    @staticmethod
    def _wait_publish_result(session: CdpSession, timeout: float = 12) -> PublishResult:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = session.evaluate("({url:location.href,text:document.body?.innerText||''})") or {}
            url = state.get("url", "")
            if isinstance(url, str) and "blog.51cto.com/" in url and "blogger/publish" not in url:
                return PublishResult(RunStatus.PUBLISHED, url=url, message="发布成功")
            if "发布成功" in state.get("text", ""):
                return PublishResult(RunStatus.PUBLISHED, url=url or None, message="发布成功")
            time.sleep(0.5)
        return PublishResult(RunStatus.UNKNOWN, message="已点击发布但结果无法确认；为防止重复，软件不会自动重试")

    def _diagnostic_failure(self, session: CdpSession, reason: str) -> PublishResult:
        snapshot = session.evaluate(
            "({url:location.href,title:document.title,ready:document.readyState,bodyText:(document.body?.innerText||'').slice(0,5000),html:document.documentElement?.outerHTML||''})"
        ) or {}
        metadata = json.dumps({key: value for key, value in snapshot.items() if key != "html"}, ensure_ascii=False, indent=2)
        html = f"<!-- BlogPilot diagnostic\n{metadata}\n-->\n{snapshot.get('html') or '<html><body>页面 HTML 为空</body></html>'}"
        diagnostic = save_diagnostic(self.diagnostic_dir, html)
        return PublishResult(RunStatus.FAILED, message=f"{reason}，诊断文件：{diagnostic}")
