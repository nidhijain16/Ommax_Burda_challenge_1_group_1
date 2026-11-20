"""
Data loader and indexer for the FACTS Topic Opportunity Scout dataset.
Loads and indexes all 10 CSV tables, resolving relationships and counting unique publishers.
"""

import csv
import os
from typing import Dict, List, Any, Set

DATA_FILES = {
    "taxonomy": "00_topic_taxonomy.csv",
    "portfolio": "01_portfolio.csv",
    "learnings": "02_learnings.csv",
    "signals": "03_signals.csv",
    "competitors": "04_competitors.csv",
    "indicators": "05_market_indicators.csv",
    "populations": "06_entity_populations.csv",
    "events": "07_regulatory_events.csv",
    "sources": "08_sources.csv",
    "spaces": "09_opportunity_spaces.csv",
}

class DataLoader:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.raw_data: Dict[str, List[Dict[str, str]]] = {}
        self.by_id: Dict[str, Dict[str, Any]] = {}
        self.by_topic: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
        self._load_all()

    def _load_csv(self, filename: str) -> List[Dict[str, str]]:
        path = os.path.join(self.data_dir, filename)
        with open(path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return [row for row in reader]

    def _load_all(self):
        for key, fname in DATA_FILES.items():
            rows = self._load_csv(fname)
            self.raw_data[key] = rows

        # Index by ID
        id_col_map = {
            "portfolio": "project_id",
            "learnings": "learning_id",
            "signals": "signal_id",
            "competitors": "competitor_id",
            "indicators": "indicator_id",
            "populations": "population_id",
            "events": "event_id",
            "sources": "source_id",
            "spaces": "context_id",  # 09_opportunity_spaces.csv uses context_id (M...)
        }

        for table_key, id_col in id_col_map.items():
            for row in self.raw_data[table_key]:
                rec_id = row.get(id_col)
                if not rec_id and table_key == "spaces":
                    rec_id = row.get("space_id")  # backwards compatibility with older exports
                if rec_id:
                    self.by_id[rec_id] = {**row, "_table": table_key}

        # Initialize by_topic
        for tax in self.raw_data["taxonomy"]:
            t_key = tax["topic_key"]
            self.by_topic[t_key] = {
                "taxonomy": tax,
                "portfolio": [],
                "learnings": [],
                "signals": [],
                "competitors": [],
                "indicators": [],
                "populations": [],
                "events": [],
                "spaces": [],
            }

        # Populate topic buckets
        for row in self.raw_data["portfolio"]:
            tk = row.get("topic_key")
            if tk in self.by_topic:
                self.by_topic[tk]["portfolio"].append(row)

        for row in self.raw_data["signals"]:
            tk = row.get("topic_key")
            if tk in self.by_topic:
                self.by_topic[tk]["signals"].append(row)

        for row in self.raw_data["competitors"]:
            tk = row.get("topic_key")
            if tk in self.by_topic:
                self.by_topic[tk]["competitors"].append(row)

        for row in self.raw_data["indicators"]:
            tk = row.get("topic_key")
            if tk in self.by_topic:
                self.by_topic[tk]["indicators"].append(row)

        for row in self.raw_data["populations"]:
            tk = row.get("topic_key")
            if tk in self.by_topic:
                self.by_topic[tk]["populations"].append(row)

        for row in self.raw_data["events"]:
            tk = row.get("topic_key")
            if tk in self.by_topic:
                self.by_topic[tk]["events"].append(row)

        for row in self.raw_data["spaces"]:
            tk = row.get("topic_key")
            if tk in self.by_topic:
                self.by_topic[tk]["spaces"].append(row)

        # Learnings map via applies_to_topic_keys pipe-separated
        for row in self.raw_data["learnings"]:
            keys = [k.strip() for k in row.get("applies_to_topic_keys", "").split("|") if k.strip()]
            for tk in keys:
                if tk in self.by_topic:
                    self.by_topic[tk]["learnings"].append(row)

    def get_source(self, source_id: str) -> Dict[str, str]:
        return self.by_id.get(source_id, {})

    def get_distinct_publishers(self, source_ids: List[str]) -> Set[str]:
        publishers = set()
        for sid in source_ids:
            src = self.get_source(sid)
            pub = src.get("publisher", "").strip()
            if pub:
                publishers.add(pub)
        return publishers

    def get_topic_dossier(self, topic_key: str) -> Dict[str, Any]:
        return self.by_topic.get(topic_key, {})

    def get_all_topics(self) -> List[Dict[str, str]]:
        return self.raw_data["taxonomy"]

