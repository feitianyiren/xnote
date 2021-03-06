# -*- coding:utf-8 -*-
# @author xupingmao <578749341@qq.com>
# @since 2018/06/07 22:10:11
# @modified 2018/11/18 15:03:16
"""
缓存的实现，考虑失效的规则如下

失效的检查策略
1. 读取时检查失效
2. 生成新的缓存时从队列中取出多个缓存进行检查

持久化策略
1. 初始化的时候从文件中读取，运行过程中直接从内存读取
2. 创建或者更新的时候持久化到文件
3. TODO 考虑持久化时的并发控制


淘汰置换规则（仅用于会失效的缓存）
1. FIFO, First In First Out
2. LRU, Least Recently Used
3. LFU, Least Frequently Used

参考redis的API
"""
from collections import OrderedDict
from .imports import *
_cache_dict = dict()

def encode_key(text):
    """编码key为文件名"""
    return text + ".json"
    # return base64.urlsafe_b64encode(text.encode("utf-8")).decode("utf-8") + ".pk"

def decode_key(text):
    """解码文件名称为key值，暂时没有使用"""
    return base64.urlsafe_b64decode(text[:-3].encode("utf-8")).decode("utf-8")


def log_debug(msg):
    # print(msg)
    pass

def log_error(msg):
    print(msg)

class CacheObj:
    """
    缓存对象，包含缓存的key和value，有一个公共的缓存队列
    每次生成一个会从缓存队列中取出一个检查是否失效，同时把自己放入队列
    TODO 提供按照大小过滤的规则
    """
    _queue = Queue()
    # 缓存的最大容量，用于集合类型
    max_size = -1

    def __init__(self, key, value, expire = -1, type = "object"):
        global _cache_dict
        
        if key is None:
            raise ValueError("key cannot be None")
        if value is None:
            raise ValueError("value cannot be None")
        if key.find("/") >= 0:
            raise ValueError("cannot contains / in key")
        if not self.is_valid_key(key):
            raise ValueError("invalid key `%s`" % key)

        self.key              = key
        self.value            = value
        self.expire           = expire
        self.expire_time      = time.time() + expire
        self.type             = type
        self.is_force_expired = False

        if type == "zset" and not isinstance(value, OrderedDict):
            value = OrderedDict(**value)
            self.value = value

        if expire < 0:
            self.expire_time = -1

        obj = _cache_dict.get(key, None)
        if obj is not None:
            obj.is_force_expired = True

        self.save()
        self._queue.put(self)

        one = self._queue.get(block=False)
        if one is not None:
            if one.is_force_expired == True:
                return
            if one.is_alive():
                self._queue.put(one)
            else:
                one.clear()

    def is_valid_key(self, key):
        return re.match(r"^[0-9a-zA-Z\[\]_\-\.\(\)\@\#,'\"\$ ]+$", key) != None

    def _get_path(self, key):
        return os.path.join(xconfig.STORAGE_DIR, key + ".json")

    def get_dump_value(self):
        if self.type == "zset":
            return dict(**self.value)
        else:
            return self.value

    def save(self):
        _cache_dict[self.key] = self
        if self.is_temp():
            return
        # save to disk
        path = self._get_path(self.key)
        obj = dict(key = self.key, 
                type = self.type,
                value = self.get_dump_value(), 
                expire_time = self.expire_time)

        encoded = json.dumps(obj)
        with open(path, "w") as fp:
            fp.write(encoded)

    def is_alive(self):
        if self.is_force_expired:
            return False
        if self.expire_time < 0:
            return True
        return time.time() < self.expire_time

    def is_temp(self):
        return self.expire_time > 0

    def get_value(self):
        if self.is_alive():
            return self.value
        self.clear()
        return None

    def clear(self):
        log_debug("clear cache %s" % self.key)
        _cache_dict.pop(self.key, None)
        if self.is_temp():
            return
        # remove from disk
        path = self._get_path(self.key)
        if os.path.exists(path):
            os.remove(path)

def cache(key=None, prefix=None, expire=600):
    """
    缓存的装饰器，会自动清理失效的缓存ge
    TODO 可以考虑缓存持久化的问题
    """
    def deco(func):
        # 先不支持keywords参数
        def handle(*args):
            if key is not None:
                cache_key = key
            elif prefix is None:
                mod = inspect.getmodule(func)
                funcname = func.__name__
                cache_key = "%s.%s%s" % (mod.__name__, funcname, args)
            else:
                cache_key = "%s%s" % (prefix, args)
            obj = _cache_dict.get(cache_key)
            if obj != None and obj.is_alive():
                # print("hit cache %s" % cache_key)
                return obj.value
            if obj != None and not obj.is_alive():
                obj.clear()
            value = func(*args)
            cache_obj = CacheObj(cache_key, value, expire)
            cache_obj.func = func
            cache_obj.args = args
            return value
        return handle
    return deco


def expire_cache(key = None, prefix = None, args = None):
    """使key对应的缓存失效，成功返回True"""
    if key == None:
        key = "%s%s" % (prefix, args)
    obj = _cache_dict.get(key)
    if obj != None:
        # 防止删除了新的cache
        obj.clear()
        obj.is_force_expired = True
        return True
    return False

def put_cache(key = None, value = None, prefix = None, args = None, expire = -1):
    """设置缓存的值"""
    if key is None:
        key = '%s%s' % (prefix, args)
    _cache_dict[key] = CacheObj(key, value, expire)

def get(key, default_value=None):
    """获取缓存的值"""
    obj = get_cache_obj(key)
    if obj is None:
        return default_value
    return obj.get_value()

get_cache = get

def get_cache_obj(key, default_value=None, type=None):
    if not is_str(key):
        raise TypeError("cache key must be string")
    obj = _cache_dict.get(key)
    if obj is None:
        return default_value
    if obj.is_alive():
        if type != None and type != obj.type:
            raise TypeError("require %s but found %s" % (type, obj.type))
        return obj
    obj.clear()
    return None

update_cache = put_cache

def update_cache_by_key(key):
    """
    直接通过key来更新缓存，前提是缓存已经存在
    """
    obj = _cache_dict.get(key)
    if obj != None:
        func = obj.func
        args = obj.args
        obj.value = func(*args)

def lpush(key, value):
    obj = get_cache_obj(key, type="list")
    if obj != None and obj.value != None:
        obj.value.insert(0, value)
        obj.save()
    else:
        obj = CacheObj(key, [value], type = "list")
        obj.save()

def lrange(key, start = 0, stop = -1):
    obj = get_cache_obj(key, type = "list")
    if obj != None and obj.value != None:
        length = len(obj.value)
        if start < 0:
            start += length
        if stop < 0:
            stop += length
        return obj.value[start: stop+1]
    else:
        return []

class SortedObject:

    def __init__(self, key, value):
        self.key = key
        self.value = value

    def __lt__(self, obj):
        return self.value < obj.value

    def __cmp__(self, obj):
        return cmp(self.value, obj.value)

def zadd(key, score, member):
    ## TODO 双写两个列表
    obj = get_cache_obj(key, type="zset")
    if obj != None and obj.value != None:
        obj.value.pop(member, None)
        obj.value[member] = score
        obj.type = "zset"
        obj.save()
    else:
        obj = CacheObj(key, OrderedDict(), type="zset")
        obj.value[member] = score
        obj.save()

def zrange(key, start, stop):
    """zset分片，不同于Python，这里是左右包含，包含start，包含stop
    :arg int start: 从0开始，负数表示倒数
    :arg int stop: 从0开始，负数表示倒数
    TODO 优化排序算法，使用有序列表+哈希表
    """
    obj = get_cache_obj(key)
    if obj != None:
        items = obj.value.items()
        if stop == -1:
            stop = len(items)
        else:
            stop += 1
        sorted_items = sorted(items, key = lambda x: x[1])
        sorted_keys = [k[0] for k in sorted_items]
        return sorted_keys[start: stop]
    return []

def zcount(key):
    obj = get_cache_obj(key)
    if obj != None:
        return len(obj.value)
    return 0

def zscore(key, member):
    obj = get_cache_obj(key)
    if obj != None:
        return obj.value.get(member, None)
    return None

def zincrby(key, increment, member):
    """通过setdefault处理并发问题"""
    obj = get_cache_obj(key)
    if obj != None:
        obj.value.setdefault(member, 0)
        obj.value[member] += increment
        # obj.value.move_to_end(member, last=True)
        obj.value[member] = obj.value.pop(member)
        if obj.max_size > 0:
            # LRU置换
            while len(obj.value) > obj.max_size:
                obj.value.popitem(last = False)
        obj.save()
    else:
        zadd(key, increment, member)

def zrem(key, member):
    obj = get_cache_obj(key)
    if obj != None:
        value = obj.value.pop(member)
        if value != None:
            obj.save()
            return 1
        return 0
    else:
        return 0

def zremrangebyrank(key, start, stop):
    '''删除zset区间'''
    obj = get_cache_obj(key)
    if obj is None:
        return 0
    members = zrange(key, start, stop)
    if len(members) == 0:
        return 0
    for member in members:
        log_debug("del %s" % member)
        obj.value.pop(member)
    obj.save()
    return len(members)

def zmaxsize(key, max_size):
    obj = get_cache_obj(key)
    if obj is None:
        return
    obj.max_size = max_size

def hset(key, field, value, expire=-1):
    try:
        obj = get_cache_obj(key, type="hash")
        if obj != None and obj.value != None:
            obj.value[field] = value
            obj.type = "hash"
            obj.save()
        else:
            obj = CacheObj(key, dict(), type = "hash")
            obj.value[field] = value
            obj.save()
    except:
        print_exc()
        return None

def hget(key, field):
    try:
        obj = get_cache_obj(key, type="hash")
        if obj != None and obj.value != None:
            return obj.value.get(field)
        else:
            return None
    except:
        print_exc()
        return None

def hdel(key, field):
    obj = get_cache_obj(key, type="hash")
    if obj != None and obj.value != None:
        if field in obj.value:
            del obj.value[field]
            return 1
        return 0
    else:
        return 0

def keys(pattern=None):
    return _cache_dict.keys()

def set(key, value, expire=-1):
    CacheObj(key, value, expire)

def delete(key):
    """del与python关键字冲突"""
    obj = get_cache_obj(key)
    if obj != None:
        obj.clear()

def prefix_del(prefix):
    """使用前缀删除"""
    keys = []
    for key in _cache_dict:
        if key.startswith(prefix):
            keys.append(key)
    for key in keys:
        obj = get_cache_obj(key)
        if obj != None:
            obj.clear()

def print_exc():
    """打印系统异常堆栈"""
    ex_type, ex, tb = sys.exc_info()
    exc_info = traceback.format_exc()
    log_error(exc_info)

def json_object_hook(dict_obj):
    return Storage(**dict_obj)

def load_dump():
    dirname = xconfig.STORAGE_DIR
    valid_ext_tuple = (".json")
    for fname in os.listdir(dirname):
        if not fname.endswith(valid_ext_tuple):
            continue
        try:
            fpath = os.path.join(dirname, fname)
            with open(fpath, "rb") as fp:
                pickled = fp.read()
                if pickled == b'':
                    continue
                if fname.endswith(".json"):
                    dict_obj = json.loads(pickled.decode("utf-8"), object_hook = json_object_hook)
                else:
                    dict_obj = pickle.loads(pickled)
                # 持久化的都是不失效的数据
                obj = CacheObj(dict_obj["key"], 
                    dict_obj["value"], -1, dict_obj.get("type", "object"))
                if obj.is_temp():
                    os.remove(fpath)
        except:
            log_error("failed to load cache %s" % fname)
            print_exc()

def clear_temp():
    for key in _cache_dict.copy():
        value = _cache_dict.get(key)
        if value != None and value.is_temp():
            value.clear()

