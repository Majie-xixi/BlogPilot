from __future__ import annotations

from contextlib import contextmanager
from html import unescape
import json
import re
import time

from blogpost.browser.cdp import CdpSession


class CategoryError(RuntimeError):
    pass


def _find_category(categories: list[dict], name: str) -> bool:
    matches = [item for item in categories if item["name"].strip() == name]
    if len(matches) > 1:
        raise CategoryError(f"个人分类“{name}”存在同名项，请在分类管理中确认后重试")
    return bool(matches)


def _append_category(fields: list[tuple[str, str]], categories: list[dict], name: str):
    fields = list(fields)
    names = [(index, key, value) for index, (key, value) in enumerate(fields) if key.startswith("name[")]
    if sorted(value.strip() for _, _, value in names if value.strip()) != sorted(item["name"].strip() for item in categories):
        raise CategoryError("分类表单与已有分类不一致，已停止以保护原有分类")
    values = dict(fields)
    expected = {item["id"]: item["name"].strip() for item in categories}
    if len(values) != len(fields) or len(expected) != len(categories):
        raise CategoryError("分类表单或已有分类包含重复标识，未提交保存")
    seen = set()
    for _, key, value in names:
        if not value.strip():
            continue
        match = re.fullmatch(r"name\[(\d+)\]", key)
        if not match:
            raise CategoryError("无法核对已有分类ID，未提交保存")
        suffix = f"[{match[1]}]"
        identities = [values[prefix + suffix] for prefix in ("id", "ccid", "custom_id") if prefix + suffix in values]
        identity = identities[0] if identities else match[1]
        if (
            any(item != identity for item in identities)
            or identity in seen
            or expected.get(identity) != value.strip()
            or "sort" + suffix not in values
        ):
            raise CategoryError("已有分类的ID、名称或排序无法对应，未提交保存")
        seen.add(identity)
    if seen != set(expected):
        raise CategoryError("已有分类ID未完整保留，未提交保存")
    orders = [int(value) for key, value in fields if key.startswith("sort[")]
    blank = [(index, key) for index, key, value in names if not value.strip()]
    if blank:
        if len(blank) != 1 or blank[0][1] != "name[]" or "sort[]" not in [key for key, _ in fields]:
            raise CategoryError("分类表单包含无法确认的空分类，已停止保存")
        fields[blank[0][0]] = ("name[]", name)
        return fields
    order = max([0, *orders]) + 1
    new_keys = {f"sort[{order}]", f"name[{order}]"}
    if new_keys.intersection(key for key, _ in fields):
        raise CategoryError("分类表单索引冲突，已停止以保护原有分类")
    return fields + [(f"sort[{order}]", str(order)), (f"name[{order}]", name)]


def ensure_personal_category(client, name: str) -> None:
    name = name.strip()
    if not name or len(name.encode("utf-16-le")) // 2 > 50:
        raise CategoryError("个人分类名称不能为空，且不能超过50个字符")
    original = client.categories()
    if _find_category(original, name):
        client.refresh(original)
        return
    if len(original) >= 50:
        raise CategoryError("51CTO个人分类已达50个，无法自动添加")
    with client.manager() as manager:
        try:
            fields = _append_category(manager.form(original), original, name)
        except (ValueError, TypeError) as exc:
            raise CategoryError("无法确认分类表单，未提交保存") from exc
        current = client.categories()
        if _find_category(current, name):
            client.refresh(current)
            return
        if current != original:
            raise CategoryError("分类列表已发生变化，请检查后重试；未提交保存")
        try:
            manager.save(fields)
        except CategoryError:
            # A lost response does not prove that the server rejected the write.
            pass
        try:
            confirmed = client.categories()
            found = _find_category(confirmed, name)
        except CategoryError as exc:
            raise CategoryError("分类创建结果无法确认，已停止且不会自动重复创建") from exc
        if not found:
            raise CategoryError("分类创建未确认成功，请检查分类管理；不会自动重复创建")
        original_ids = {item["id"] for item in original}
        if [item for item in confirmed if item["id"] in original_ids] != original:
            raise CategoryError("保存后已有分类发生变化，已停止发布，请检查分类管理")
        client.refresh(confirmed)


_REQUEST = """async ({save,fields}) => {
if(location.origin!=='https://blog.51cto.com')throw Error('unexpected origin');
const headers={'X-Requested-With':'XMLHttpRequest'};
let body;
if(save){
  body=new URLSearchParams(fields);
  const param=document.querySelector('meta[name="csrf-param"]')?.content;
  const token=document.querySelector('meta[name="csrf-token"]')?.content;
  if(param&&token)body.set(param,token);
  headers['Content-Type']='application/x-www-form-urlencoded; charset=UTF-8';
}
const path=save?'/blogger-ajax/cate-manage':'/blogger-ajax/get-user-cate';
const response=await fetch(path,{method:save?'POST':'GET',credentials:'same-origin',
  cache:'no-store',redirect:'error',signal:AbortSignal.timeout(6000),headers,body});
if(!response.ok||new URL(response.url).pathname!==path)throw Error('category request failed');
return await response.json();
}"""

_FORM = """(() => {
if(location.origin!=='https://blog.51cto.com'||location.pathname!=='/creative-center/classify')return null;
const root=document.querySelector('#classifyList');
if(!root||document.readyState!=='complete')return null;
return [...root.querySelectorAll('input[name]')]
 .filter(el=>!/(csrf|token|secret|password)/i.test(el.name)).map(el=>[el.name,el.value]);
})()"""


class CategoryClient:
    def __init__(self, chrome, session: CdpSession):
        self.chrome, self.session = chrome, session

    def _evaluate(self, expression):
        try:
            return self.session.evaluate(expression)
        except (OSError, RuntimeError, ValueError) as exc:
            raise CategoryError("51CTO分类请求失败或登录状态无法确认，已停止") from exc

    def categories(self) -> list[dict]:
        result = self._evaluate(f"({_REQUEST})({{save:false}})")
        try:
            if type(result["status"]) is not int or result["status"] != 1 or not isinstance(result["data"]["custom"], list):
                raise ValueError("invalid category response")
            items = result["data"]["custom"]
            if any(not isinstance(item["name"], str) or not str(item["custom_id"]).strip() or item["custom_id"] is None for item in items):
                raise ValueError("invalid category entry")
            return [dict(id=str(item["custom_id"]), name=unescape(item["name"])) for item in items]
        except (KeyError, TypeError, ValueError) as exc:
            raise CategoryError("无法读取当前账号的个人分类，未创建分类") from exc

    @contextmanager
    def manager(self):
        target = self.chrome.open_tab("https://blog.51cto.com/creative-center/classify")
        websocket = target.get("webSocketDebuggerUrl")
        if not websocket:
            raise CategoryError("无法连接分类管理页，未创建分类")
        with CdpSession(websocket, timeout=8) as session:
            try:
                yield CategoryClient(self.chrome, session)
            finally:
                try:
                    session.command("Page.close")
                except (OSError, RuntimeError):
                    pass

    def form(self, categories):
        deadline = time.monotonic() + 6
        expected = sorted(item["name"].strip() for item in categories)
        while time.monotonic() < deadline:
            try:
                fields = self._evaluate(_FORM)
            except CategoryError:
                fields = None
            if isinstance(fields, list) and all(isinstance(pair, list) and len(pair) == 2 and all(isinstance(value, str) for value in pair) for pair in fields):
                names = sorted(value.strip() for key, value in fields if key.startswith("name[") and value.strip())
                if names == expected:
                    return [tuple(pair) for pair in fields]
            time.sleep(0.2)
        raise CategoryError("分类管理表单未就绪或列表已变化，未提交保存")

    def save(self, fields):
        result = self._evaluate(f"({_REQUEST})({json.dumps(dict(save=True, fields=fields), ensure_ascii=False)})")
        return isinstance(result, dict) and result.get("status") == 1

    def refresh(self, categories):
        expression = """(items => {
const list=document.querySelector('#selfType_list');
if(!list)return false;
const options=items.map(item=>{
  const li=document.createElement('li');li.className='el-select-dropdown__item';
  li.setAttribute('value',item.id);const span=document.createElement('span');
  span.textContent=item.name;li.append(span);return li;
});
list.replaceChildren(...options);return true;
})"""
        if self._evaluate(f"{expression}({json.dumps(categories, ensure_ascii=False)})") is not True:
            raise CategoryError("分类已确认，但编辑器列表刷新失败，请重试")
