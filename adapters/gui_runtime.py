"""Use the real ChatGPT web interface in a persistent browser profile."""

import os
from pathlib import Path
import re
import subprocess
import time
from urllib.parse import urlsplit

if __package__:
    from .pdf_export import find_browser
else:
    from pdf_export import find_browser


GUI_SETTINGS = {
    "codex": {
        "url": "https://chatgpt.com/",
        "input": ('#prompt-textarea', '[data-testid="prompt-textarea"]', '[contenteditable="true"][role="textbox"]'),
        "send": ('[data-testid="send-button"]', '#composer-submit-button', 'button[aria-label="Send prompt"]'),
        "answer": ('[data-message-author-role="assistant"] .markdown', '[data-message-author-role="assistant"]', '[data-chatgpt-search-unit-key$=":assistant"] .markdown', '[data-chatgpt-search-unit-key$=":assistant"]'),
        "stop": ('[data-testid="stop-button"]', 'button[aria-label*="Stop streaming"]', 'button[aria-label*="停止"]'),
    },
}


# Extract structure and original TeX rather than innerText, which loses bold,
# headings and formulas (and may duplicate the visual and accessible math).
MARKDOWN_SCRIPT = r"""root => {
  function convert(node) {
    if (node.nodeType === Node.TEXT_NODE) return node.textContent;
    if (node.nodeType !== Node.ELEMENT_NODE) return '';
    const tag = node.tagName.toLowerCase();
    if (['script', 'style', 'button', 'svg'].includes(tag) || node.getAttribute('aria-hidden') === 'true') return '';
    if (node.matches('.katex-display, .katex, mjx-container')) {
      const annotation = node.querySelector('annotation[encoding="application/x-tex"]');
      const tex = annotation?.textContent || node.getAttribute('data-tex');
      if (tex) {
        const display = node.matches('.katex-display') || node.getAttribute('display') === 'true';
        return display ? '\n\n$$' + tex + '$$\n\n' : '$' + tex + '$';
      }
    }
    if (tag === 'pre') return '\n\n```\n' + (node.querySelector('code') || node).textContent + '\n```\n\n';
    if (tag === 'code') return '`' + node.textContent + '`';
    if (tag === 'table') {
      const rows = [...node.querySelectorAll('tr')].map(row => [...row.children].map(cell => convert(cell).trim().replace(/\|/g, '\\|').replace(/\n/g, ' ')));
      if (!rows.length) return '';
      const line = row => '| ' + row.join(' | ') + ' |';
      return '\n\n' + [line(rows[0]), line(rows[0].map(() => '---')), ...rows.slice(1).map(line)].join('\n') + '\n\n';
    }
    const text = [...node.childNodes].map(convert).join('');
    if (/^h[1-6]$/.test(tag)) return '\n\n' + '#'.repeat(Number(tag[1])) + ' ' + text.trim() + '\n\n';
    if (tag === 'strong' || tag === 'b') return '**' + text.trim() + '**';
    if (tag === 'em' || tag === 'i') return '*' + text.trim() + '*';
    if (tag === 'br') return '\n';
    if (tag === 'li') {
      const index = [...node.parentElement.children].indexOf(node) + 1;
      return '\n' + (node.parentElement.tagName === 'OL' ? index + '. ' : '- ') + text.trim().replace(/\n/g, '\n  ');
    }
    if (['p', 'div', 'section', 'ul', 'ol', 'blockquote'].includes(tag)) return '\n\n' + text.trim() + '\n\n';
    return text;
  }
  return convert(root).replace(/\n[ \t]+\n/g, '\n\n').replace(/\n{3,}/g, '\n\n').trim();
}"""


def _visible(page, selectors):
    for selector in selectors:
        matches = page.locator(selector)
        for index in range(matches.count() - 1, -1, -1):
            item = matches.nth(index)
            if item.is_visible():
                return item
    return None


def _answer(page, settings):
    item = _visible(page, settings["answer"])
    return item.evaluate(MARKDOWN_SCRIPT) if item is not None else ""


def _login_required(page):
    # is_visible() also catches login overlays marked aria-hidden.
    if page.locator('[data-slot="dialog-overlay"][data-state="open"]:visible, [role="dialog"][aria-modal="true"]:visible').count():
        return True
    if page.locator('input[type="password"]:visible, input[autocomplete="one-time-code"]:visible, input[placeholder*="验证码"]:visible').count():
        return True
    pattern = re.compile(r"^(?!.*(?:退出|注销|Log\s*out|Sign\s*out)).*(?:登录|登入|注册|Log\s*in|Sign\s*in)", re.I)
    for role in ("button", "link"):
        matches = page.get_by_role(role, name=pattern)
        if any(matches.nth(index).is_visible() for index in range(matches.count())):
            return True
    return False


def _chat_ready(page, settings):
    expected = urlsplit(settings["url"])
    actual = urlsplit(page.url)
    if actual.hostname != expected.hostname or not actual.path.startswith(expected.path):
        return False
    if _login_required(page):
        return False
    return True


def _connect_browser(playwright, directory, url):
    """Connect to a separate browser process so disconnecting cannot close login."""
    from playwright.sync_api import Error as PlaywrightError

    port_file = directory / "DevToolsActivePort"

    def connect():
        lines = port_file.read_text(encoding="utf-8").splitlines()
        port = int(lines[0])
        if not 0 < port < 65536 or not lines[1].startswith("/devtools/browser/"):
            raise ValueError("无效的浏览器连接地址。")
        return playwright.chromium.connect_over_cdp(f"ws://127.0.0.1:{port}{lines[1]}", timeout=1500)

    try:
        return connect()
    except (OSError, ValueError, IndexError, PlaywrightError):
        pass
    subprocess.Popen(
        [find_browser(), "--remote-debugging-port=0", "--remote-debugging-address=127.0.0.1",
         f"--user-data-dir={directory}", "--no-first-run", "--no-default-browser-check", url],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=(subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP) if os.name == "nt" else 0,
        start_new_session=os.name != "nt",
    )
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            return connect()
        except (OSError, ValueError, IndexError, PlaywrightError):
            time.sleep(0.25)
    raise RuntimeError("无法连接独立浏览器。若旧任务仍占用此专用窗口，请关闭该窗口后重试。")


def _wait_for_composer(page, settings, timeout):
    from playwright.sync_api import Error as PlaywrightError

    deadline = time.monotonic() + timeout
    ready_since = None
    while time.monotonic() < deadline:
        if page.is_closed():
            raise RuntimeError("聊天页面已关闭，请重新开始 GUI 生成。")
        try:
            composer = _visible(page, settings["input"])
            if composer is not None and composer.is_editable() and _chat_ready(page, settings):
                composer.click(trial=True, timeout=750)
                ready_since = ready_since or time.monotonic()
                if time.monotonic() - ready_since >= 2:
                    return composer
            else:
                ready_since = None
            page.wait_for_timeout(500)
        except PlaywrightError:
            # Login redirects briefly destroy the DOM; keep waiting for it.
            ready_since = None
            time.sleep(0.25)
    raise RuntimeError("等待登录或输入框超时；浏览器窗口已保留，请完成登录后重新点击生成。")


def _submit_prompt(page, settings, prompt, timeout):
    """Wait through login transitions; click Send only once after trial checks."""
    from playwright.sync_api import Error as PlaywrightError

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        composer = _wait_for_composer(page, settings, max(0, deadline - time.monotonic()))
        try:
            if not _chat_ready(page, settings):
                continue
            composer.fill(prompt, timeout=2000)
            page.wait_for_timeout(500)
            if not _chat_ready(page, settings):
                continue
            send = _visible(page, settings["send"])
            if send is not None:
                send.click(trial=True, timeout=1000)
            else:
                composer.click(trial=True, timeout=1000)
            if not _chat_ready(page, settings):
                continue
        except PlaywrightError:
            # No submission yet: a login dialog/navigation can safely be waited out.
            page.wait_for_timeout(250)
            continue
        baseline = _answer(page, settings)
        try:
            if send is not None:
                send.click(timeout=3000, no_wait_after=True)
            else:
                composer.press("Enter", timeout=3000)
        except PlaywrightError:
            raise RuntimeError("发送状态未确认，请在保留的网页中检查是否已发送，再决定重试，避免重复提交。") from None
        return baseline
    raise RuntimeError("等待登录完成后发送超时；浏览器窗口已保留，未自动重复发送。")


def _finished(page, settings):
    item = _visible(page, settings["answer"])
    if item is None:
        return False
    return item.evaluate("""node => {
      const turn = node.closest('article') || node.closest('[data-testid="union_message"]')
        || node.closest('[data-chatgpt-search-unit-key$=":assistant"]')
        || node.closest('[data-message-id]')?.parentElement || node.parentElement;
      const controls = turn.querySelectorAll('[data-testid="copy-turn-action-button"], [data-testid*="copy"], button[aria-label*="Copy"], button[aria-label*="复制"], [data-foundation-type="receive-message-action-bar"]');
      return [...controls].some(button => button.getClientRects().length && !button.disabled);
    }""")


def generate_gui(provider, prompt, timeout=1200):
    if provider not in GUI_SETTINGS:
        raise ValueError("该平台不支持 GUI 方式。")
    try:
        from playwright.sync_api import sync_playwright, Error as PlaywrightError
    except ImportError:
        raise RuntimeError("GUI 方式需要 Playwright，请点击“一键配置环境”自动安装。") from None
    settings = GUI_SETTINGS[provider]
    directory = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share"))) / "MathCompSkill" / "browser" / provider
    directory.mkdir(parents=True, exist_ok=True)
    print("[*] 正在打开独立浏览器；首次请登录，并在网页中选择需要的模型。登录状态将自动保留。", flush=True)
    try:
        with sync_playwright() as playwright:
            browser = _connect_browser(playwright, directory, settings["url"])
            context = browser.contexts[0]
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(10000)
            page.goto(settings["url"], wait_until="domcontentloaded", timeout=60000)
            print(f"[*] 等待登录或验证完成（最多 {timeout} 秒），窗口会保留。", flush=True)
            composer = _wait_for_composer(page, settings, timeout)

            # Each module starts a separate conversation when the site offers it.
            new_chat = page.get_by_role("button", name=re.compile(r"^(新对话|开启新对话|创建新对话|New chat)$", re.I))
            if new_chat.count() and new_chat.first.is_visible():
                new_chat.first.click()
                composer = _wait_for_composer(page, settings, timeout)
            print("[*] 登录与聊天页检查通过，准备填写提示词。", flush=True)
            baseline = _submit_prompt(page, settings, prompt, timeout)
            print("[*] 提示词已提交，正在等待网页回答...", flush=True)

            deadline = time.monotonic() + timeout
            last_text, stable_since = "", time.monotonic()
            while time.monotonic() < deadline:
                if page.is_closed():
                    raise RuntimeError("聊天页面已关闭，无法读取回答。")
                try:
                    text = _answer(page, settings)
                    if text != last_text:
                        last_text, stable_since = text, time.monotonic()
                    generating = _visible(page, settings["stop"]) is not None
                    # Only accept a stable, complete answer from the current turn.
                    if text and text != baseline and not generating and _finished(page, settings) and time.monotonic() - stable_since >= 5:
                        return text
                    page.wait_for_timeout(1000)
                except PlaywrightError:
                    time.sleep(0.25)
            raise RuntimeError("等待网页回答超时；浏览器窗口已保留，可在网页中查看进度。")
    except PlaywrightError as error:
        raise RuntimeError(f"GUI 调用失败：{error}。浏览器不会被自动关闭，请完成登录或验证后重试。") from None
