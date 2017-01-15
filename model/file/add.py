from BaseHandler import *
import FileDB
from FileDB import FileDO

class handler(BaseHandler):

    def execute(self):
        name = self.get_argument("name", "")
        tags = self.get_argument("tags", "")
        key  = self.get_argument("key", "")

        file = FileDO(name)
        file.atime = dateutil.get_seconds()
        file.satime = dateutil.format_time()
        file.mtime = dateutil.get_seconds()
        file.smtime = dateutil.format_time()
        file.ctime = dateutil.get_seconds()
        file.sctime = dateutil.format_time()
        file.parent_id = 0
        error = ""
        try:
            if name != '':
                f = FileDB.insert(file)
                raise web.seeother("/file/edit?name=%s" % quote(name))
        except Exception as e:
            error = e
        self.render("file/add.html", key = "", name = key, tags = tags, error=error)