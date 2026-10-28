import os
from dotenv import load_dotenv

from .orchestrator import Orchestrator


def main() -> None:
    load_dotenv()
    if not os.getenv("DEEPSEEK_API_KEY"):
        raise SystemExit("Не найден DEEPSEEK_API_KEY. Скопируйте .env.example в .env и добавьте API-ключ.")

    agent = Orchestrator(
        model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        max_steps=int(os.getenv("MAX_STEPS", "8")),
        max_tool_calls=int(os.getenv("MAX_TOOL_CALLS", "10")),
        max_history_messages=int(os.getenv("MAX_HISTORY_MESSAGES", "32")),
    )
    print("Linux vs Windows Agent — вводите утверждение о Linux. Для выхода: exit / quit\n")

    while True:
        try:
            text = input("Вы: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nWindows забирает победу по тайм-ауту. Пока!")
            break

        if text.lower() in {"exit", "quit", "выход"}:
            print("Агент: Хорошо, заседание комитета по выбору ОС закрыто.")
            break
        if not text:
            continue

        try:
            print(f"\nАгент: {agent.run(text)}\n")
        except Exception as exc:
            print(f"\nОшибка: {type(exc).__name__}: {exc}\n")


if __name__ == "__main__":
    main()
