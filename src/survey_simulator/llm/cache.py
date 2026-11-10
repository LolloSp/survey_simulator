"""Cache su disco delle risposte LLM, indicizzata per impronta della richiesta.

Un file JSON per voce in `<dir>/<aa>/<hash>.json`. La stessa richiesta (stesso
provider, modello, prompt, schema, effort e variante) non torna mai in rete:
è la base della riproducibilità e del risparmio nei run ripetuti.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from survey_simulator.llm.client import LLMResponse


@dataclass
class ResponseCache:
    directory: Path

    def path_for(self, key: str) -> Path:
        return Path(self.directory) / key[:2] / f"{key}.json"

    def get(self, key: str) -> LLMResponse | None:
        path = self.path_for(key)
        if not path.is_file():
            return None
        data = json.loads(path.read_bytes().decode("utf-8"))
        return LLMResponse.from_dict({**data, "from_cache": True})

    def put(self, key: str, response: LLMResponse) -> Path:
        path = self.path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = response.to_dict()
        data["from_cache"] = False
        path.write_bytes(
            (json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
        )
        return path

    def __contains__(self, key: str) -> bool:
        return self.path_for(key).is_file()

    def count(self) -> int:
        return (
            sum(1 for _ in Path(self.directory).glob("*/*.json"))
            if Path(self.directory).is_dir()
            else 0
        )
