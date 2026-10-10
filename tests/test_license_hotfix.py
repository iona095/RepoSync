import importlib.util
from email.message import Message
import pathlib
import tempfile
import unittest
from unittest.mock import patch

here = pathlib.Path(__file__).parent
spec = importlib.util.spec_from_file_location('repo_license_gate', here.parent/'scripts'/'audit_build_licenses.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

MIT = '''MIT License
Copyright (c) 2019-2026 Benedikt Reinartz
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND.
'''

class Dist:
    def __init__(self, version, licensefile):
        self.version = version
        self._licensefile = licensefile
        self.files = ['clr_loader-0.3.1.dist-info/licenses/LICENSE'] if licensefile else []
        self.metadata = Message()
    def locate_file(self, entry):
        return self._licensefile

class TestLicenseGate(unittest.TestCase):
    def test_only_exact_version_with_installed_mit_license_passes(self):
        with tempfile.TemporaryDirectory() as td:
            p=pathlib.Path(td)/'LICENSE'
            p.write_text(MIT,encoding='utf8')
            self.assertTrue(mod.is_verified_clr_loader_mit(Dist('0.3.1',p),[p]))
            self.assertFalse(mod.is_verified_clr_loader_mit(Dist('0.3.2',p),[p]))
            self.assertFalse(mod.is_verified_clr_loader_mit(Dist('0.3.1',p),[]))
    def test_bad_legal_text_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p=pathlib.Path(td)/'LICENSE'
            for text in ['MIT License\n', 'All rights reserved', MIT.replace('Benedikt Reinartz','Someone Else'), MIT.replace('permission notice shall be included','permission notice shall be excluded')]:
                p.write_text(text,encoding='utf8')
                self.assertFalse(mod.is_verified_clr_loader_mit(Dist('0.3.1',p),[p]),text[:60])
    def test_license_text_is_bundled_and_notice_records_override(self):
        with tempfile.TemporaryDirectory() as td:
            td=pathlib.Path(td)
            p=td/'LICENSE';p.write_text(MIT,encoding='utf8')
            dist=Dist('0.3.1',p)
            with patch.object(mod.im,'distribution',return_value=dist), patch.dict(mod.LICENSES,{'clr_loader':('MIT',)},clear=True):
                result=mod.run(td/'out')
            self.assertEqual(result,0)
            self.assertTrue((td/'out'/'clr_loader-0.3.1-0.txt').exists())
            self.assertIn('installed distribution LICENSE', (td/'out'/'BUILD-THIRD-PARTY-NOTICES.txt').read_text())
    def test_no_legal_text_blocks_gate(self):
        with tempfile.TemporaryDirectory() as td:
            td=pathlib.Path(td)
            with patch.object(mod.im,'distribution',return_value=Dist('0.3.1',None)), patch.dict(mod.LICENSES,{'clr_loader':('MIT',)},clear=True):
                self.assertEqual(mod.run(td/'out'),2)

if __name__ == '__main__':unittest.main()
