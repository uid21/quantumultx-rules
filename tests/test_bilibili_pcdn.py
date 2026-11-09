import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "rules", Path(__file__).resolve().parents[1] / "scripts/update_bilibili_pcdn.py"
)
rules = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rules)

MBGA = """
const knownP2pCdnDomainPattern = createRetrieKeywordFilter([
  '302ppio', '302kodo', '.mcdn.bilivideo', 'szbdyd.com',
  '.nexusedgeio.com', '.ahdohpiechei.com', // provider comment
  '.mountaintoys.cn', '.bvmlt.top',
  'upos-sz-mirror14b.bilivideo.com'
]);
return subdomain.includes('302');
"""
PCDN = """
# mixed-service upstream
DOMAIN-SUFFIX,mcdn.bilivideo.cn
DOMAIN-SUFFIX,szbdyd.com
DOMAIN-REGEX,.*pcdn.*biliapi.net
DOMAIN-SUFFIX,xycdn.com
DOMAIN-SUFFIX,p2ptun.qq.com
DOMAIN-SUFFIX,youku.com
DOMAIN-REGEX,.*p2p.*qq.com
"""


class RuleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "sources").mkdir()
        self.manual = {"basic": [["host-wildcard", "*pcdn*.biliapi.net"]], "extended": []}
        self.write_manual()

    def write_manual(self):
        (self.root / "sources/bilibili-pcdn-manual.json").write_text(json.dumps(self.manual))

    def update(self, **kwargs):
        with patch.object(rules, "fetch_source", side_effect=[MBGA, PCDN]):
            return rules.update(self.root, **kwargs)

    def test_generated_rules_block_known_pcdn_and_allow_normal_traffic(self):
        output = rules.build(self.root, {"mbga": MBGA, "pcdn": PCDN})
        basic = output[rules.OUTPUTS[0]]
        extended = output[rules.OUTPUTS[1]]
        parsed = lambda text: [tuple(line.split(", ")[:2]) for line in text.splitlines() if line and not line.startswith("#")]
        a, b = parsed(basic), parsed(extended)
        for host in ("stun-pcdn-test.biliapi.net", "a.mcdn.bilivideo.cn", "a.mcdn.bilivideo.com", "v1d.szbdyd.com"):
            self.assertTrue(any(rules.matches(rule, host) for rule in a), host)
        for host in ("upos-sz-302ppio.bilivideo.com", "upos-sz-302abc.bilivideo.com", "video.nexusedgeio.com"):
            self.assertFalse(any(rules.matches(rule, host) for rule in a), host)
            self.assertTrue(any(rules.matches(rule, host) for rule in b), host)
        for host in (*rules.SAFE_HOSTS, "foopcdn.evilbiliapi.net", "szbdyd.com.evil.example", "p2ptun.qq.com"):
            self.assertFalse(any(rules.matches(rule, host) for rule in b), host)
        self.assertTrue(set(a) <= set(b))

    def test_manual_addition_survives_regeneration(self):
        self.manual["basic"].append(["host", "local-pcdn.example.net"])
        self.write_manual()
        self.update()
        self.update()
        self.assertIn("host, local-pcdn.example.net, reject", (self.root / rules.OUTPUTS[0]).read_text())

    def test_idempotent_and_check_does_not_write(self):
        self.assertEqual(3, len(self.update(check=True)))
        self.assertFalse((self.root / rules.OUTPUTS[0]).exists())
        self.assertEqual(3, len(self.update()))
        times = [(self.root / name).stat().st_mtime_ns for name in rules.OUTPUTS]
        self.assertEqual([], self.update())
        self.assertEqual(times, [(self.root / name).stat().st_mtime_ns for name in rules.OUTPUTS])

    def test_download_failure_keeps_every_existing_output(self):
        self.update()
        before = {name: (self.root / name).read_bytes() for name in rules.OUTPUTS}
        with patch.object(rules, "fetch_source", side_effect=[MBGA, rules.UpdateError("network down")]):
            with self.assertRaises(rules.UpdateError):
                rules.update(self.root)
        self.assertEqual(before, {name: (self.root / name).read_bytes() for name in rules.OUTPUTS})

    def test_bad_structure_keeps_every_existing_output(self):
        self.update()
        before = {name: (self.root / name).read_bytes() for name in rules.OUTPUTS}
        with patch.object(rules, "fetch_source", side_effect=["<html>error</html>", PCDN]):
            with self.assertRaises(rules.UpdateError):
                rules.update(self.root)
        self.assertEqual(before, {name: (self.root / name).read_bytes() for name in rules.OUTPUTS})

    def test_upstream_cannot_add_broad_bilibili_blocks(self):
        for domain in (".bilibili.com", ".biliapi.net", ".bilivideo.net", ".akamaized.net"):
            text = MBGA.replace("'.bvmlt.top'", repr(domain))
            with self.subTest(domain=domain), self.assertRaises(rules.UpdateError):
                rules.build(self.root, {"mbga": text, "pcdn": PCDN})

    def test_upstream_code_is_rejected(self):
        for text in (MBGA.replace("'302ppio'", "getSecret()"), MBGA.replace("'302ppio'", "'newKeyword'")):
            with self.assertRaises(rules.UpdateError):
                rules.parse_mbga(text)

    def test_invalid_manual_rule_stops_update(self):
        self.manual["basic"].append(["host-suffix", "bilibili.com"])
        self.write_manual()
        with self.assertRaises(rules.UpdateError):
            self.update()
        self.assertFalse((self.root / rules.OUTPUTS[0]).exists())

    def test_collection_does_not_import_unrelated_platforms(self):
        selected = rules.parse_pcdn(PCDN)
        self.assertEqual(3, len(selected))
        self.assertNotIn(("host-suffix", "xycdn.com"), selected)
        with self.assertRaises(rules.UpdateError):
            rules.parse_pcdn("<html>blocked</html>")

    def test_output_has_only_native_qx_reject_rules(self):
        output = rules.build(self.root, {"mbga": MBGA, "pcdn": PCDN})
        for name in rules.OUTPUTS[:2]:
            lines = [x for x in output[name].splitlines() if x and not x.startswith("#")]
            self.assertEqual(lines, sorted(set(lines)))
            for line in lines:
                kind, host, policy = line.split(", ")
                self.assertEqual("reject", policy)
                rules.validate_rule((kind, host))


if __name__ == "__main__":
    unittest.main()
