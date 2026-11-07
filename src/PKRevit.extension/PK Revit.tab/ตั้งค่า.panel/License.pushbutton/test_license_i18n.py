# -*- coding: utf-8 -*-
"""unit test ของ revotech.i18n และ revotech.license (รันนอก Revit): python test_license_i18n.py"""
import os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "..", "lib"))
from revotech import i18n
from revotech import license as lic

KEY = u"ABCDE-12345-FGHIJ-67890"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["PKREVIT_HOME"] = self.tmp
        i18n.reset_cache()

    def tearDown(self):
        os.environ.pop("PKREVIT_HOME", None)
        i18n.reset_cache()


class I18nTest(Base):
    def test_default_thai(self):
        self.assertEqual(i18n.get_language(), "th")
        self.assertEqual(i18n.t("ui.close"), u"ปิด")

    def test_switch_and_persist(self):
        i18n.set_language("en")
        self.assertEqual(i18n.t("ui.close"), u"Close")
        i18n.reset_cache()
        self.assertEqual(i18n.get_language(), "en")   # อ่านจากไฟล์
        self.assertTrue(os.path.isfile(i18n.settings_path()))

    def test_keeps_other_settings(self):
        i18n.save_settings({"foo": 1})
        i18n.set_language("lo")
        s = i18n.load_settings()
        self.assertEqual(s["foo"], 1)
        self.assertEqual(s["language"], "lo")

    def test_format(self):
        i18n.set_language("en", persist=False)
        self.assertEqual(i18n.t("ui.select_first", what=u"a column", hint=u"x"),
                         u"Please select a column first. x")

    def test_fallback_lo_to_en(self):
        i18n.set_language("lo", persist=False)
        self.assertEqual(i18n.t("ui.close"), u"ປິດ")
        self.assertEqual(i18n.t("ui.summary.done"), u"Done")  # ไม่มีลาว -> อังกฤษ

    def test_unknown_key_and_lang(self):
        self.assertEqual(i18n.t("no.such.key"), "no.such.key")
        i18n.set_language("en", persist=False)
        self.assertEqual(i18n.set_language("xx", persist=False), "en")
        self.assertEqual(i18n.normalize_lang("EN-us"), "en")
        self.assertIsNone(i18n.normalize_lang(""))

    def test_corrupt_settings(self):
        with open(i18n.settings_path(), "w") as f:
            f.write("{not json")
        self.assertEqual(i18n.load_settings(), {})
        self.assertEqual(i18n.get_language(), "th")

    def test_table_complete_th_en(self):
        self.assertEqual(i18n.missing_translations(lang="th"), [])
        self.assertEqual(i18n.missing_translations(lang="en"), [])

    def test_placeholders_match(self):
        import re
        for k, v in i18n.STRINGS.items():
            sets = set(frozenset(re.findall(r"\{(\w+)\}", s))
                       for s in v.values())
            self.assertEqual(len(sets), 1, k)


class LicenseTest(Base):
    def test_key_format(self):
        self.assertTrue(lic.check_key_format(KEY).ok)
        self.assertTrue(lic.check_key_format(u" abcde12345fghij67890 ").ok)
        self.assertEqual(lic.check_key_format(u"").reason, lic.EMPTY_KEY)
        self.assertEqual(lic.check_key_format(u"ABC").reason, lic.BAD_FORMAT)
        self.assertEqual(lic.mask_key(KEY), u"*****-*****-*****-67890")

    def test_fingerprint(self):
        a = lic.machine_fingerprint(["PC1", "aa:bb"])
        self.assertEqual(a, lic.machine_fingerprint(["AA:BB", " pc1 ", ""]))
        self.assertNotEqual(a, lic.machine_fingerprint(["PC2", "aa:bb"]))
        self.assertEqual(len(a), 20)
        self.assertNotIn("pc1", a.lower())

    def test_machine_id_stable(self):
        self.assertEqual(lic.machine_id(), lic.machine_id())

    def test_check_activation_limit(self):
        ok, _, ms = lic.check_activation([], "A")
        self.assertTrue(ok)
        ok, _, ms = lic.check_activation(ms, "B")
        self.assertTrue(ok)
        ok, r, ms2 = lic.check_activation(ms, "C")
        self.assertFalse(ok)
        self.assertEqual(r, lic.MACHINE_LIMIT)
        self.assertEqual(ms2, ["A", "B"])
        self.assertTrue(lic.check_activation(ms, "A")[0])   # เครื่องเดิมผ่าน

    def test_inmemory_validator(self):
        v = lic.InMemoryValidator({KEY: {"machines": []}})
        self.assertTrue(v.validate(KEY, "A").ok)
        self.assertTrue(v.validate(KEY, "B").ok)
        r = v.validate(KEY, "C")
        self.assertFalse(r.ok)
        self.assertEqual(r.reason, lic.MACHINE_LIMIT)
        self.assertEqual(v.validate(u"AAAAA-AAAAA-AAAAA-AAAAA", "A").reason,
                         lic.UNKNOWN_KEY)
        v.records[KEY]["revoked"] = True
        self.assertEqual(v.validate(KEY, "A").reason, lic.REVOKED)

    def test_dev_mode(self):
        self.assertTrue(lic.is_dev_mode({"PKREVIT_LICENSE_MODE": " DEV "}))
        self.assertFalse(lic.is_dev_mode({}))
        self.assertIsInstance(lic.default_validator({"PKREVIT_LICENSE_MODE": "dev"}),
                              lic.DevValidator)
        self.assertTrue(lic.DevValidator().validate("", "A").ok)

    def test_default_no_server(self):
        os.environ.pop(lic.ENV_MODE, None)
        r = lic.activate(KEY, mid="A")
        self.assertFalse(r.ok)
        self.assertEqual(r.reason, lic.NO_SERVER)
        self.assertFalse(os.path.exists(lic.state_path()))   # ไม่บันทึกถ้าไม่ผ่าน

    def test_activate_and_status(self):
        v = lic.InMemoryValidator({KEY: {"machines": []}})
        self.assertEqual(lic.status_of(lic.load_state(), "A", False)[0], "unlicensed")
        self.assertTrue(lic.activate(KEY, v, "A").ok)
        st = lic.load_state()
        self.assertEqual(lic.status_of(st, "A", False),
                         ("licensed", u"*****-*****-*****-67890"))
        self.assertEqual(lic.status_of(st, "B", False)[0], "other_machine")
        self.assertEqual(lic.status_of({}, "A", True)[0], "dev")

    def test_messages_exist_for_all_reasons(self):
        for code in (lic.OK, lic.EMPTY_KEY, lic.BAD_FORMAT, lic.UNKNOWN_KEY,
                     lic.REVOKED, lic.MACHINE_LIMIT, lic.IN_USE_ELSEWHERE,
                     lic.NO_SERVER, lic.SERVER_ERROR, lic.DEV_MODE):
            for lg in ("th", "en"):
                i18n.set_language(lg, persist=False)
                m = lic.Result(False, code, {"limit": 2}).message()
                self.assertFalse(m.startswith("license.reason."), code)


if __name__ == "__main__":
    unittest.main()
