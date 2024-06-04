# Usage
# ~~~~~
# import lru_cache
# cache = lru_cache.LRUCache(size=2)
# cache.put("key_0", "value_0")
# cache.put("key_1", "value_1")
# cache.put("key_2", "value_2")
# print(len(cache))
# print(cache.get("key_0"))  # None
# print(cache.get("key_1"))  # value_1
# "key_0" in cache           # False
# "key_1" in cache           # True
#
# Resources
# ~~~~~~~~~
# https://www.geeksforgeeks.org/lru-cache-in-python-using-ordereddict/amp

from collections import OrderedDict  # All OrderedDict operations are O(1)

__all__ = ["LRUCache"]

class LRUCache:
    def __init__(self, size):
        self.size = size
        self.lru_cache = OrderedDict()

    def __iter__(self):
        return self.lru_cache.__iter__()

    def __len__(self):
        return len(self.lru_cache)

    def get(self, key):
        if key not in self.lru_cache:
            return None
        else:
            self.lru_cache.move_to_end(key)  # update recently used item
            return self.lru_cache[key]

    def get_list(self):
        return(list(self.lru_cache.values()))

    def put(self, key, value):
        self.lru_cache[key] = value
        self.lru_cache.move_to_end(key)  # update recently used item
        if len(self.lru_cache) > self.size:
            self.lru_cache.popitem(last=False)  # remove least recent key/value
