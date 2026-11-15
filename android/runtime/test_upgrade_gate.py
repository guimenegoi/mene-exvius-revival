"""The Java first-run gate must not accept the rev9 receipt before rev10 install."""
from __future__ import annotations

import unittest
import json
from pathlib import Path

from patch_first_run import patch_installed_manifest_gate, patch_data_pack_origin


METHOD = '''
.method private static installedManifestComplete(Landroid/content/Context;)Z
    .locals 10
    const/4 v0, 0x0
    :try_start_0
    invoke-static {p0}, Lcom/exvius/local/DataUpdates;->installed(Landroid/content/Context;)Lorg/json/JSONObject;
    move-result-object v1

    .line 86
    .local v1, "current":Lorg/json/JSONObject;
    const-string v2, "packs"
    invoke-virtual {v1, v2}, Lorg/json/JSONObject;->optJSONArray(Ljava/lang/String;)Lorg/json/JSONArray;
    move-result-object v2
    const/4 v4, 0x1

    if-ge v3, v4, :cond_0
    goto :goto_2
    :cond_0
    return v4
    :goto_2
    return v0
.end method
'''


class UpgradeGateTests(unittest.TestCase):
    def test_rev10_and_20_packs_are_required(self):
        out = patch_installed_manifest_gate(METHOD)
        self.assertIn('const-string v2, "revision"', out)
        self.assertIn('const/16 v3, 0xa', out)
        self.assertIn('if-eq v2, v3, :rev10_ready', out)
        self.assertIn('const/16 v5, 0x14', out)
        self.assertIn('if-ge v3, v5, :cond_0', out)
        self.assertIn('return v4', out)
        with self.assertRaisesRegex(ValueError, 'stacked patch'):
            patch_installed_manifest_gate(out)

    def test_pack_urls_match_rev10_manifest_and_app_origin_is_untouched(self):
        data = json.loads((Path(__file__).resolve().parents[2] / "data/latest.json").read_text())
        pack_origin = "https://github.com/CreamySeaman6/Data/releases/download/"
        self.assertEqual(len(data["packs"]), 20)
        self.assertTrue(all(row["url"].startswith(pack_origin) for row in data["packs"]))
        old = "https://github.com/Elvlin/exvius-offline/releases/download/"
        sample = (".method private static downloadApp()V\n" + old + "\n.end method\n"
                  ".method private static validate(Lorg/json/JSONObject;)V\n"
                  + old + "\n.end method\n" + old)
        updated = patch_data_pack_origin(sample)
        self.assertEqual(updated.count(pack_origin), 1)
        self.assertEqual(updated.count(old), 2)
        with self.assertRaisesRegex(ValueError, "duplicate patch"):
            patch_data_pack_origin(updated)
        with self.assertRaisesRegex(ValueError, "validator"):
            patch_data_pack_origin("nothing")

    def test_unknown_upstream_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            patch_installed_manifest_gate('')
        with self.assertRaisesRegex(ValueError, 'Unrecognized'):
            patch_installed_manifest_gate(METHOD.replace('const/4 v4, 0x1', 'const/4 v4, 0x0'))


if __name__ == '__main__':
    unittest.main()
