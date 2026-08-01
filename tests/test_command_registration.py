import ast
import unittest
from pathlib import Path


MAIN = Path(__file__).resolve().parents[1] / 'main.py'


class CommandRegistrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = ast.parse(MAIN.read_text(encoding='utf-8'))
        cls.plugin = next(
            node for node in cls.tree.body if isinstance(node, ast.ClassDef) and node.name == 'YuanSyncPlugin'
        )
        cls.methods = {
            node.name: node
            for node in cls.plugin.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }

    def _decorator_exprs(self, method_name: str) -> list[str]:
        node = self.methods[method_name]
        return [ast.unparse(decorator) for decorator in node.decorator_list]

    def test_only_sync_commands_are_registered(self):
        registered_methods = {
            method_name
            for method_name, method in self.methods.items()
            if any(expr.startswith('filter.command(') for expr in self._decorator_exprs(method_name))
        }
        self.assertEqual({'sync_agents_command', 'sync_levels_command'}, registered_methods)

    def test_sync_commands_use_expected_names_and_schemas(self):
        expected = {
            'sync_agents_command': ("filter.command('同步密探')", "self._trigger_sync_webhook('2.0', '密探')"),
            'sync_levels_command': ("filter.command('同步关卡')", "self._trigger_sync_webhook('3.0', '关卡')"),
        }
        for method_name, (decorator, call) in expected.items():
            self.assertIn(decorator, self._decorator_exprs(method_name))
            self.assertIn(call, ast.unparse(self.methods[method_name]))

    def test_sync_commands_use_runtime_guards(self):
        for method_name in ('sync_agents_command', 'sync_levels_command'):
            decorators = self._decorator_exprs(method_name)
            method_src = ast.unparse(self.methods[method_name])
            self.assertNotIn('filter.permission_type(filter.PermissionType.ADMIN)', decorators)
            self.assertNotIn(
                'filter.event_message_type(filter.EventMessageType.PRIVATE_MESSAGE)',
                decorators,
            )
            self.assertIn('self._is_admin(event)', method_src)
            self.assertIn('self._ensure_private_chat(event)', method_src)

if __name__ == '__main__':
    unittest.main()
