import asyncio
import json
from dataclasses import dataclass
from typing import Iterable
from urllib import error, request

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register


SYNC_WEBHOOK_ENDPOINT = "http://192.168.31.66:28793/webhook"
HTTP_TIMEOUT_SECONDS = 15


@dataclass(slots=True)
class SyncWebhookResult:
    ok: bool
    status_code: int | None
    detail: str


@register("feishu_yuan_helper", "mrsnake", "代号鸢同步插件", "1.1.0")
class YuanSyncPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    async def initialize(self):
        logger.info("代号鸢同步插件已初始化")

    @filter.command("同步密探")
    async def sync_agents_command(self, event: AstrMessageEvent, *_command_args):
        """触发密探数据同步。"""
        private_guard = self._ensure_private_chat(event)
        if private_guard is not None:
            yield private_guard
            event.stop_event()
            return
        if not self._is_admin(event):
            yield event.plain_result(self._format_message("权限不足", ["只有管理员可以触发同步任务。"]))
            event.stop_event()
            return
        result = await self._trigger_sync_webhook("2.0", "密探")
        yield event.plain_result(self._format_message("密探同步", [result.detail]))
        event.stop_event()

    @filter.command("同步关卡")
    async def sync_levels_command(self, event: AstrMessageEvent, *_command_args):
        """触发关卡数据同步。"""
        private_guard = self._ensure_private_chat(event)
        if private_guard is not None:
            yield private_guard
            event.stop_event()
            return
        if not self._is_admin(event):
            yield event.plain_result(self._format_message("权限不足", ["只有管理员可以触发同步任务。"]))
            event.stop_event()
            return
        result = await self._trigger_sync_webhook("3.0", "关卡")
        yield event.plain_result(self._format_message("关卡同步", [result.detail]))
        event.stop_event()

    async def terminate(self):
        logger.info("代号鸢同步插件已卸载")

    async def _trigger_sync_webhook(self, schema: str, target_name: str) -> SyncWebhookResult:
        payload = {"schema": schema}
        headers = {
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
        }

        def do_request() -> tuple[int | None, str]:
            body = json.dumps(payload).encode("utf-8")
            req = request.Request(SYNC_WEBHOOK_ENDPOINT, data=body, headers=headers, method="POST")
            try:
                with request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as response:
                    charset = response.headers.get_content_charset("utf-8")
                    return response.getcode(), response.read().decode(charset, errors="replace")
            except error.HTTPError as http_error:
                charset = (
                    http_error.headers.get_content_charset("utf-8")
                    if http_error.headers is not None
                    else "utf-8"
                )
                body_text = http_error.read().decode(charset, errors="replace")
                return http_error.code, body_text

        try:
            status_code, raw_text = await asyncio.to_thread(do_request)
        except Exception as exc:
            logger.exception("同步 Webhook 请求失败 target=%s schema=%s", target_name, schema)
            return SyncWebhookResult(
                ok=False,
                status_code=None,
                detail=f"{target_name}同步触发失败：{exc}",
            )

        logger.info(
            "同步 Webhook 请求完成 target=%s schema=%s status=%s",
            target_name,
            schema,
            status_code,
        )
        if status_code is not None and 200 <= status_code < 300:
            return SyncWebhookResult(
                ok=True,
                status_code=status_code,
                detail=f"{target_name}同步已触发。",
            )

        response_summary = raw_text.strip()[:120]
        detail = f"{target_name}同步触发失败：HTTP {status_code}"
        if response_summary:
            detail = f"{detail}，{response_summary}"
        return SyncWebhookResult(ok=False, status_code=status_code, detail=detail)

    @staticmethod
    def _is_admin(event: AstrMessageEvent) -> bool:
        checker = getattr(event, "is_admin", None)
        if callable(checker):
            return bool(checker())
        return getattr(event, "role", None) == "admin"

    def _ensure_private_chat(self, event: AstrMessageEvent):
        checker = getattr(event, "is_private_chat", None)
        if callable(checker):
            is_private_chat = bool(checker())
        else:
            is_private_chat = getattr(event, "get_platform_name", lambda: "")() == "private"
        if is_private_chat:
            return None
        return event.plain_result(self._format_message("请私聊使用", ["这个指令仅支持在私聊中使用。"]))

    @staticmethod
    def _format_message(title: str, lines: Iterable[str]) -> str:
        rendered_lines = [line for line in lines if line]
        if not rendered_lines:
            return f"【{title}】"
        return "\n".join([f"【{title}】", *(f"• {line}" for line in rendered_lines)])
