# encoding=utf-8
import sys
sys.path.insert(1, "lib")

import unittest
import json
import web

import xmanager
import xutils
import xtemplate
import xconfig
import xtables

def init():
    xtables.init()
    xconfig.IS_TEST = True
    xconfig.port = "1234"
    var_env = dict()
    app = web.application(list(), var_env, autoreload=False)
    mgr = xmanager.init(app, var_env)
    mgr.reload()
    return app

app = init()

class TestMain(unittest.TestCase):

    def test_render_text(self):
        value = xtemplate.render_text("Hello,{{name}}", name="World")
        self.assertEqual(b"Hello,World", value)

    def test_render(self):
        value = app.request("/test").data
        self.assertEqual(b"success", value)

    def test_recent_files(self):
        value = app.request("/file/recent_edit?_type=json").data
        json_value = value.decode("utf-8")
        files = json.loads(json_value)["files"]
        print("files=%s" % len(files))

    def test_fs_func(self):
        import handlers.fs.fs as fs
        item0, item1 = fs.getpathlist("/fs/test/")
        self.assertEqual("/fs/", item0.path)
        self.assertEqual("/fs/test/", item1.path)

        item0, item1, item2 = fs.getpathlist("C:/data/name/")
        self.assertEqual("C:/", item0.path)
        self.assertEqual("C:/data/", item1.path)
        self.assertEqual("C:/data/name/", item2.path)

    def check_200(self, url):
        response = app.request(url)
        self.assertEqual("200 OK", response.status)

    def check_303(self, url):
        response = app.request(url)
        self.assertEqual("303 See Other", response.status)

    def check_404(self, url):
        response = app.request(url)
        self.assertEqual("404 Not Found", response.status)

    def test_file(self):
        self.check_200("/file/recent_edit")

    def test_fs(self):
        self.check_200("/fs//")
        self.check_200("/fs//?_type=json")
        self.check_200("/data/data.db")

    def test_sys(self):
        self.check_200("/system/sys")
        self.check_200("/system/user_admin")
        self.check_200("/system/sys_var_admin")
        self.check_200("/system/crontab")

    def test_tools(self):
        self.check_200("/tools/sql")
        self.check_200("/tools/color")

    def test_backup_info(self):
        self.check_200("/system/backup_info")

    def test_notfound(self):
        self.check_404("/nosuchfile")






