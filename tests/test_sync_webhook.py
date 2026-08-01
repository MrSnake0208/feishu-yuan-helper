import asyncio
import importlib
import json
import sys
import types
import unittest
from unittest.mock import Mock, patch


class _Filter:
    @staticmethod
    def command(*_args, **_kwargs):
        return lambda target: target


class _Headers:
    @staticmethod
    def get_content_charset(default):
        return default


class _Response:
    def __init__(self, status_code=200, body=b'ok'):
        self.status_code = status_code
        self.body = body
        self.headers = _Headers()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def getcode(self):
        return self.status_code

    def read(self):
        return self.body


def _install_astrbot_stubs():
    astrbot = types.ModuleType('astrbot')
    api = types.ModuleType('astrbot.api')
    event = types.ModuleType('astrbot.api.event')
    star = types.ModuleType('astrbot.api.star')

    api.logger = Mock()
    event.AstrMessageEvent = object
    event.filter = _Filter
    star.Context = object
    star.Star = object
    star.register = lambda *_args, **_kwargs: lambda target: target

    stubs = {
        'astrbot': astrbot,
        'astrbot.api': api,
        'astrbot.api.event': event,
        'astrbot.api.star': star,
    }
    sys.modules.update(stubs)


_install_astrbot_stubs()
main = importlib.import_module('main')


class SyncWebhookTests(unittest.TestCase):
    def setUp(self):
        self.plugin = main.YuanSyncPlugin.__new__(main.YuanSyncPlugin)

    def test_posts_expected_json_to_sync_endpoint(self):
        with patch.object(main.request, 'urlopen', return_value=_Response()) as urlopen:
            result = asyncio.run(self.plugin._trigger_sync_webhook('2.0', '密探'))

        req = urlopen.call_args.args[0]
        self.assertEqual(main.SYNC_WEBHOOK_ENDPOINT, req.full_url)
        self.assertEqual('POST', req.get_method())
        self.assertEqual({'schema': '2.0'}, json.loads(req.data.decode('utf-8')))
        self.assertEqual('application/json', req.get_header('Content-type'))
        self.assertEqual(main.HTTP_TIMEOUT_SECONDS, urlopen.call_args.kwargs['timeout'])
        self.assertTrue(result.ok)
        self.assertEqual(200, result.status_code)
        self.assertEqual('密探同步已触发。', result.detail)

    def test_reports_non_success_status_without_retrying(self):
        with patch.object(main.request, 'urlopen', return_value=_Response(503, b'busy')) as urlopen:
            result = asyncio.run(self.plugin._trigger_sync_webhook('3.0', '关卡'))

        self.assertEqual(1, urlopen.call_count)
        self.assertFalse(result.ok)
        self.assertEqual(503, result.status_code)
        self.assertEqual('关卡同步触发失败：HTTP 503，busy', result.detail)

    def test_reports_connection_errors_without_retrying(self):
        with patch.object(main.request, 'urlopen', side_effect=OSError('offline')) as urlopen:
            result = asyncio.run(self.plugin._trigger_sync_webhook('3.0', '关卡'))

        self.assertEqual(1, urlopen.call_count)
        self.assertFalse(result.ok)
        self.assertIsNone(result.status_code)
        self.assertEqual('关卡同步触发失败：offline', result.detail)

if __name__ == '__main__':
    unittest.main()
