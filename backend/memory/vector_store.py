class VectorStore:
    def __init__(self):
        self.data = []

    def add(self, item):
        self.data.append(item)

    def search(self, query):
        return self.data[:5]