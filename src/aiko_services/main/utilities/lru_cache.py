# Usage
# ~~~~~
# import lru_cache
# cache = lru_cache.LRUCache(size=2)
# cache.put("key_0", "value_0")
# cache.put("key_1", "value_1")
# evicted = cache.put("key_2", "value_2")  # ("key_0", "value_0")
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
        """Add or refresh an item.  Returns the (key, value) that this put
        evicted, or None.  A caller that holds state of its own for each
        key needs to know, because the eviction is otherwise silent"""

        evicted = None
        self.lru_cache[key] = value
        self.lru_cache.move_to_end(key)  # update recently used item
        if len(self.lru_cache) > self.size:
            evicted = self.lru_cache.popitem(last=False)  # least recent
        return evicted

    def resize(self, size):
        """Change the maximum.  A smaller one evicts the least recently
        used items at once, and returns each evicted (key, value)"""

        if size < 1:
            raise ValueError(f"LRUCache size must be 1 or more: {size}")
        self.size = size
        evicted = []
        while len(self.lru_cache) > self.size:
            evicted.append(self.lru_cache.popitem(last=False))
        return evicted
