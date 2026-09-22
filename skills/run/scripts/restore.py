"""Print the exact command to restore an MCP server that mcp-prune backed
up when it recommended removing it (see backup.py).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from backup import BACKUP_DIR


def main():
    """CLI entry point: `python restore.py <server-name>`.

    @returns: None. Prints the `claude mcp add-json` command to restore
        the named server, or an explanation if no backup exists for it.
    """
    if len(sys.argv) != 2:
        print("usage: python restore.py <server-name>")
        return
    name = sys.argv[1]
    path = BACKUP_DIR / f"{name}.json"
    if not path.exists():
        print(f"'{name}' 백업을 찾을 수 없습니다 - mcp-prune 리포트에서 제거를 권장한 적이 없는 서버입니다.")
        return
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    payload = json.dumps(snapshot["add_json"], ensure_ascii=False)
    print(f"{snapshot['removed_at']}에 백업된 설정입니다. 아래 명령어로 복원하세요:")
    print()
    print(f"claude mcp add-json {name} '{payload}' --scope user")


if __name__ == "__main__":
    main()
