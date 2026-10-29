import json
import shutil
import subprocess
import unittest

from blogpost.publishers.personal_categories import _REQUEST


@unittest.skipUnless(shutil.which("node"), "Node.js needed to execute browser request fixture")
class CategoryRequestBridgeTests(unittest.TestCase):
    def run_bridge(self, arguments, *, ok=True, origin="https://blog.51cto.com", path=None):
        harness = r"""
const input=JSON.parse(require('fs').readFileSync(0,'utf8'));
global.location={origin:input.origin};
global.document={querySelector:s=>s.includes('csrf-param')?{content:'_csrf'}:{content:'synthetic-csrf-value'}};
const calls=[];
global.fetch=async(path,options)=>{
 calls.push({path,method:options.method,body:options.body?[...options.body.entries()]:null,
  credentials:options.credentials,redirect:options.redirect,cache:options.cache});
 return {ok:input.ok,url:input.origin+(input.path||path),json:async()=>({status:1,data:{custom:[]}})};
};
(async()=>{try{await eval('('+input.source+')')(input.arguments);
 console.log(JSON.stringify({calls,success:true}));}
 catch(error){console.log(JSON.stringify({calls,success:false}));}})();
"""
        result = subprocess.run(
            [shutil.which("node"), "-e", harness],
            input=json.dumps(dict(source=_REQUEST, arguments=arguments, ok=ok, origin=origin, path=path)),
            text=True, encoding="utf-8", capture_output=True, check=True, timeout=8,
        )
        return json.loads(result.stdout)

    def test_listing_is_a_read_only_same_origin_uncached_request(self):
        result = self.run_bridge(dict(save=False))
        self.assertTrue(result["success"])
        self.assertEqual(result["calls"], [dict(path="/blogger-ajax/get-user-cate", method="GET", body=None,
                                              credentials="same-origin", redirect="error", cache="no-store")])

    def test_save_preserves_all_pairs_and_adds_csrf_inside_browser(self):
        fields = [["id[4]", "42"], ["name[4]", "已有 & 分类"], ["sort[4]", "4"], ["name[5]", 'AI "工具"']]
        result = self.run_bridge(dict(save=True, fields=fields))
        self.assertTrue(result["success"])
        self.assertEqual(len(result["calls"]), 1)
        self.assertEqual(result["calls"][0]["method"], "POST")
        self.assertEqual(result["calls"][0]["body"], fields + [["_csrf", "synthetic-csrf-value"]])

    def test_failed_http_wrong_origin_or_login_redirect_stops(self):
        self.assertFalse(self.run_bridge(dict(save=False), ok=False)["success"])
        wrong_origin = self.run_bridge(dict(save=True, fields=[]), origin="https://example.test")
        self.assertFalse(wrong_origin["success"])
        self.assertEqual(wrong_origin["calls"], [])
        self.assertFalse(self.run_bridge(dict(save=False), path="/login")["success"])
