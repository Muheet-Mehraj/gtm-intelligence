class Tracer:
    def __init__(self):
        self.spans = []

    def start(self, name: str):
        self.spans.append({"event": name})

    def get_trace(self):
        return self.spans