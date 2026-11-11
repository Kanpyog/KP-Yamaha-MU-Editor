"""Complete, per-operation receive diagnostics, independent of the GUI log limit."""
from datetime import datetime
import json
from pathlib import Path


class ReadTrace:
    def __init__(self, data_dir, label):
        folder = Path(data_dir) / 'logs'
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        self.path = folder / f'read_{stamp}.jsonl'
        self.file = self.path.open('x', encoding='utf-8')
        self.error = ''
        self.record('start', label=label)

    def record(self, event, **values):
        if self.error:
            return
        try:
            entry = {'time': datetime.now().astimezone().isoformat(), 'event': event, **values}
            self.file.write(json.dumps(entry, ensure_ascii=False) + '\n')
        except OSError as exc:
            self.error = str(exc)

    def close(self):
        try:
            self.file.close()
        except OSError as exc:
            self.error = str(exc)
