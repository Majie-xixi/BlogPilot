from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
import time

from blogpost.browser.cdp import CdpSession
from blogpost.browser.chrome import ChromeController
from blogpost.domain import Article, PublishResult, RunStatus
from blogpost.publishers.diagnostics import save_diagnostic
from blogpost.publishers.cto51_profile import ProfileSnapshot, fetch_profile_snapshot


PUBLISH_URL = "https://blog.51cto.com/blogger/publish"
HOME_URL = "https://blog.51cto.com/"


CURRENT_PROFILE_SCRIPT = """(() => {
const normalize=(value)=>{
  try {
    const url=new URL(value, location.href);
    const href=url.href.replace(/\\/$/,'');
    return /^https:\\/\\/blog\\.51cto\\.com\\/u_\\d+$/.test(href)?href:'';
  } catch {
    return '';
  }
};
const anchors=[...document.querySelectorAll('a[href]')];
const byText=anchors.find(a=>normalize(a.href)&&/我的博客|个人主页|主页/.test(a.textContent.trim()));
if(byText)return normalize(byText.href);
const current=normalize(location.href);
if(current)return current;
return anchors.map(a=>normalize(a.href)).find(Boolean)||'';
})()"""


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


HANDLE_SENSITIVE_REVIEW_SCRIPT = """(() => {
const visible=(el)=>!!el&&el.offsetParent!==null;
const text=document.body?.innerText||'';
const detected=/内容涉及敏感信息|进入待审核|非常抱歉[\\s\\S]{0,120}敏感信息/.test(text);
const button=[...document.querySelectorAll('button')]
  .find(el=>visible(el)&&el.textContent.trim()==='继续发布');
const match=text.match(/博客(?:正文|标题)[：:]\\s*([^\\n\\r]+)/);
if(detected&&button)button.click();
return {
  detected,
  clicked:detected&&!!button,
  term:match?.[1]?.trim()||''
};
})()"""


def build_settings_script(
    category: str,
    secondary_category: str = "编程 Agent",
    personal_category: str = "AI",
) -> str:
    category_json = json.dumps(category, ensure_ascii=False)
    secondary_json = json.dumps(secondary_category, ensure_ascii=False)
    personal_json = json.dumps(personal_category, ensure_ascii=False)
    return f"""(async () => {{
const category={category_json}, secondary={secondary_json}, personal={personal_json};
const visible=(el)=>!!el&&el.offsetParent!==null;
const pause=(ms)=>new Promise(resolve=>setTimeout(resolve,ms));
const exact=(text)=>[...document.querySelectorAll('label,button,li,span,div')]
  .filter(el=>visible(el)&&el.textContent.trim()===text)
  .sort((a,b)=>a.childElementCount-b.childElementCount)[0];
const clickChoice=(selector,text)=>{{
  const item=[...document.querySelectorAll(selector)].find(el=>visible(el)&&el.textContent.trim()===text);
  if(!item)return false;
  item.click();
  return true;
}};
if(![...document.querySelectorAll('.select_item_check')].some(el=>el.textContent.trim()===category)){{
  clickChoice('.select_item',category);
  await pause(180);
}}
let selectedSecondary=[...document.querySelectorAll('.second-types-item-check')].find(visible);
if(!selectedSecondary){{
  const secondaryItems=[...document.querySelectorAll('.second-types-item')].filter(visible);
  const wanted=secondaryItems.find(el=>el.textContent.trim()===secondary)||secondaryItems[0];
  if(wanted){{wanted.click();await pause(120);}}
}}
const personalInput=document.querySelector('#selfType');
const categoryOk=[...document.querySelectorAll('.select_item_check')].some(el=>el.textContent.trim()===category);
const secondaryOk=!document.querySelector('.second-types-item')||!![...document.querySelectorAll('.second-types-item-check')].find(visible);
const personalOk=!!personalInput&&personalInput.value.trim()===personal;
const typeInput=[...document.querySelectorAll('input')].find(el=>visible(el)&&(el.placeholder||'').includes('文章类型'));
let originalOk=!!typeInput && (typeInput.value||'').includes('原创');
if(typeInput&&!originalOk){{
  typeInput.click();
  const original=exact('原创');
  if(original){{original.click();originalOk=true;}}
}}
const release=[...document.querySelectorAll('button.release')].find(visible);
return {{categoryOk,secondaryOk,personalOk,originalOk,releaseReady:!!release,typeValue:typeInput?.value||'',personalValue:personalInput?.value||'',url:location.href}};
}})()"""


@dataclass(slots=True)
class Cto51Publisher:
    chrome: ChromeController
    diagnostic_dir: Path
    expected_profile_url: str = ""
    secondary_category: str = "编程 Agent"
    personal_category: str = "AI"

    def open_login(self) -> None:
        self.chrome.start("https://blog.51cto.com/login")

    def current_profile_url(self) -> str:
        return self._current_profile_url()

    def current_profile_snapshot(self) -> ProfileSnapshot:
        profile_url = self.current_profile_url()
        if not profile_url:
            raise ValueError("未识别到当前登录的 51CTO 博客主页")
        return fetch_profile_snapshot(profile_url)

    @staticmethod
    def _profile_url_from_target(target: dict) -> str:
        websocket_url = target.get("webSocketDebuggerUrl")
        if not websocket_url:
            return ""
        try:
            with CdpSession(websocket_url) as session:
                value = session.evaluate(CURRENT_PROFILE_SCRIPT)
        except Exception:
            return ""
        return value if isinstance(value, str) else ""

    def has_publication_on(self, day: date) -> bool | None:
        """Check the public profile without starting the automation browser."""
        try:
            return self.profile_status().has_publication_on(day)
        except Exception:
            return None

    def profile_status(self) -> ProfileSnapshot:
        if not self.expected_profile_url:
            raise ValueError("请先在设置中填写目标 51CTO 博客主页")
        return fetch_profile_snapshot(self.expected_profile_url)

    def publish(self, article: Article, category: str, dry_run: bool) -> PublishResult:
        try:
            if self.expected_profile_url:
                current_profile = self._current_profile_url()
                expected = self.expected_profile_url.rstrip("/")
                if not current_profile:
                    return PublishResult(
                        RunStatus.FAILED,
                        message=f"无法确认 51CTO 登录账号；目标账号：{expected}，请重新登录",
                    )
                if current_profile.rstrip("/") != expected:
                    return PublishResult(
                        RunStatus.FAILED,
                        message=f"51CTO 账号不匹配，已停止发布。当前：{current_profile}；目标：{expected}",
                    )
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
                settings = session.evaluate(
                    build_settings_script(
                        category,
                        self.secondary_category,
                        self.personal_category,
                    )
                ) or {}
                if not settings.get("personalOk"):
                    settings["personalOk"] = self._select_personal_category(
                        session,
                        self.personal_category,
                    )
                required = (
                    settings.get("categoryOk"),
                    settings.get("secondaryOk"),
                    settings.get("personalOk"),
                    settings.get("originalOk"),
                    settings.get("releaseReady"),
                )
                if not all(required):
                    missing = [
                        name
                        for name, ok in (
                            ("文章分类", settings.get("categoryOk")),
                            ("二级分类", settings.get("secondaryOk")),
                            ("个人分类", settings.get("personalOk")),
                            ("文章类型", settings.get("originalOk")),
                            ("发布按钮", settings.get("releaseReady")),
                        )
                        if not ok
                    ]
                    return self._diagnostic_failure(
                        session,
                        f"51CTO 发布设置未完成：{'、'.join(missing)}",
                    )

                if dry_run:
                    return PublishResult(
                        RunStatus.SKIPPED,
                        message="安全试运行已填写文章、文章分类和个人分类，未点击最终发布",
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

    def _current_profile_url(self) -> str:
        if self.chrome.port is None:
            self.chrome.start(HOME_URL)
            target = self.chrome.wait_for_target(HOME_URL)
        else:
            targets = [
                target
                for target in self.chrome.list_targets()
                if target.get("type") == "page"
                and "blog.51cto.com" in str(target.get("url", ""))
            ]
            for target in targets:
                value = self._profile_url_from_target(target)
                if value:
                    return value
            target = next(
                (
                    target
                    for target in targets
                    if str(target.get("url", "")).startswith(HOME_URL)
                ),
                None,
            ) or self.chrome.open_tab(HOME_URL)
        websocket_url = target.get("webSocketDebuggerUrl")
        if not websocket_url:
            return ""
        with CdpSession(websocket_url) as session:
            self._wait_page_content(session, HOME_URL)
            value = session.evaluate(CURRENT_PROFILE_SCRIPT)
            if isinstance(value, str) and value:
                return value
            value = session.evaluate(
                "[...document.querySelectorAll('a[href]')].find(a=>a.textContent.trim()==='我的博客'&&/\\/u_\\d+\\/?$/.test(a.href))?.href||''"
            )
        return value if isinstance(value, str) else ""

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
    def _wait_page_content(session: CdpSession, url_prefix: str, timeout: float = 15) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = session.evaluate(
                "({url:location.href,ready:document.readyState,text:(document.body?.innerText||'').length})"
            ) or {}
            if (
                str(state.get("url", "")).startswith(url_prefix)
                and state.get("ready") in {"interactive", "complete"}
                and int(state.get("text", 0)) > 100
            ):
                return
            time.sleep(0.2)
        raise TimeoutError(f"51CTO 页面加载超时：{url_prefix}")

    @staticmethod
    def _wait_for_value(session: CdpSession, expression: str, timeout: float = 12) -> str:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = session.evaluate(expression)
            if isinstance(value, str) and value.strip():
                return value.strip()
            time.sleep(0.2)
        return ""

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

    @classmethod
    def _select_personal_category(
        cls,
        session: CdpSession,
        category: str,
        timeout: float = 5,
    ) -> bool:
        category_json = json.dumps(category, ensure_ascii=False)
        if session.evaluate(
            f"document.querySelector('#selfType')?.value.trim()==={category_json}"
        ):
            return True
        option_expression = (
            "[...document.querySelectorAll('#selfType_list li')]"
            f".find(el=>el.offsetParent!==null&&el.textContent.trim()==={category_json})"
        )
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not session.evaluate(f"!!({option_expression})"):
                if not cls._click_center(session, "document.querySelector('#selfType')"):
                    return False
                time.sleep(0.5)
            if cls._click_center(session, option_expression):
                time.sleep(0.4)
            if session.evaluate(
                f"document.querySelector('#selfType')?.value.trim()==={category_json}"
            ):
                return True
            time.sleep(0.2)
        return False

    @staticmethod
    def _click_center(session: CdpSession, element_expression: str) -> bool:
        point = session.evaluate(
            f"(() => {{const el={element_expression};"
            "if(!el||el.offsetParent===null)return null;"
            "const r=el.getBoundingClientRect();"
            "return {x:r.left+r.width/2,y:r.top+r.height/2};})()"
        )
        if not isinstance(point, dict):
            return False
        params = {
            "x": point["x"],
            "y": point["y"],
            "button": "left",
            "clickCount": 1,
        }
        session.command("Input.dispatchMouseEvent", {"type": "mousePressed", **params})
        session.command("Input.dispatchMouseEvent", {"type": "mouseReleased", **params})
        return True

    @staticmethod
    def _wait_publish_result(session: CdpSession, timeout: float = 12) -> PublishResult:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            review = session.evaluate(HANDLE_SENSITIVE_REVIEW_SCRIPT) or {}
            if review.get("detected") and review.get("clicked"):
                term = str(review.get("term", "")).strip()[:40]
                term_detail = f"（平台提示：{term}）" if term else ""
                return PublishResult(
                    RunStatus.UNKNOWN,
                    message=(
                        f"已自动确认继续发布，文章正在等待 51CTO 审核{term_detail}；"
                        "为防止重复，软件不会自动重试"
                    ),
                )
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
