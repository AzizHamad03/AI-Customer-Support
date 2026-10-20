from pathlib import Path


PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


def load_prompt(name):
    return (PROMPTS_DIR / f"{name}.md").read_text(
        encoding="utf-8"
    ).strip()