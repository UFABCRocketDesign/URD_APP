import os

class Logger:
    def __init__(self, filename):
        self.filename = filename
        self.file = open(self.filename, "a", buffering=1)  # line-buffered

    def write_header(self, headers: list[str]):
        """
        Escreve cabeçalho no arquivo (apenas uma vez).
        """
        line = "\t".join(headers) + "\n"
        self.file.write(line)
        self.file.flush()
        os.fsync(self.file.fileno())

    def save_line(self, *args):
        """
        Salva linha com tabulação.
        """
        line = "\t".join(str(x) for x in args) + "\n"
        self.file.write(line)
        self.file.flush()
        os.fsync(self.file.fileno())

    def close(self):
        if not self.file.closed:
            self.file.close()
