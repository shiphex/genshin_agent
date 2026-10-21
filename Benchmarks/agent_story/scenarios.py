"""Scenario references resolve only against the fingerprinted development set."""
from copy import deepcopy

from Benchmarks.support.common import BENCH, file_hash, read_json


def load_scenarios(root, path=None):
    suite = read_json(path or BENCH / "agent_story/scenarios.json")
    questions_path = root / "rag/eval/questions.json"
    if file_hash(questions_path) != suite["question_bank_sha256"]:
        raise ValueError("question bank fingerprint mismatch; revise the scenario binding explicitly")
    document = read_json(questions_path)
    questions = {q["id"]: q for q in document["questions"]}
    scenes = suite["scenarios"]
    if len({s["id"] for s in scenes}) != len(scenes):
        raise ValueError("duplicate scenario ID")
    for scene in scenes:
        if scene["group"] not in {"tools", "memory", "boundary"} or not scene["turns"]:
            raise ValueError("invalid scenario group or empty turns")
        scene["reference_material"] = [deepcopy(questions[qid]) for qid in scene["question_ids"]]
        scene["criteria"] = [{"id": f"c{i + 1}", "text": text, "required": True}
                             for i, text in enumerate(scene["required_criteria"])]
        for question in scene["reference_material"]:
            scene["criteria"].extend({"id": f"{question['id']}-c{i + 1}", "text": text, "required": True}
                                     for i, text in enumerate(question["criteria"]))
        for turn in scene["turns"]:
            if "question_id" in turn and turn["question_id"] not in scene["question_ids"]:
                raise ValueError("turn references a question outside the scenario")
    return suite


def public_turns(scene):
    references = {q["id"]: q for q in scene["reference_material"]}
    return [{"content": (references[t["question_id"]]["question"] if "question_id" in t else t["content"])}
            for t in scene["turns"]]
