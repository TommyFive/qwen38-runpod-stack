import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('privacy', Path(__file__).resolve().parents[1] / 'scripts/privacy-check.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class PrivacyScanTests(unittest.TestCase):
    def test_unknown_personal_paths_hosts_and_ips(self):
        fixtures = ['/Users/' + 'newperson/project', '/home/' + 'engineer/.ssh/config',
                    'node.tail' + 'a1b2c3.ts.net', 'ssh root@' + 'build.internal',
                    'host=' + '198.18.' + '12.3', 'pod_id: ' + 'abc123def456xy',
                    'https://user:' + 'pass@host.example']
        for value in fixtures:
            self.assertTrue(m.findings(value), value)

    def test_reviewed_technical_values_are_allowed(self):
        for value in ['127.0.0.1', '0.0.0.0', '192.0.2.10', '198.51.100.2',
                      '203.0.113.3', 'pod.example.ts.net', '/home/runner/work/project',
                      '$HOME/.runpod/key', 'opencv-python==4.10.0.84']:
            self.assertFalse(m.findings(value), value)

    def test_new_commit_metadata(self):
        self.assertTrue(m.metadata_findings('Contributor <person@' + 'private.invalid>'))
        self.assertFalse(m.metadata_findings('TommyFive <8273791+TommyFive@users.noreply.github.com>'))


if __name__ == '__main__':
    unittest.main()
