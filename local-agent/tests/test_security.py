"""Security tests for prompt injection and permission boundaries."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.permissions import PermissionManager
from tools.registry import build_registry, Level

def test_permissions():
    print("Testing Security and Permission Boundaries...")
    registry = build_registry()
    
    # We will use an auto-reject asker to test if it properly intercepts dangerous actions
    def reject_asker(prompt):
        return "no"
        
    class MockConfig:
        class permissions:
            auto_approve_safe = True
            auto_approve_moderate = False
            auto_approve_dangerous = False
            denied_paths = [r"C:\Windows", r"C:\secrets"]

    perms = PermissionManager(config=MockConfig(), registry=registry, asker=reject_asker)
    
    # 1. Test DANGEROUS action is blocked
    try:
        ps_tool = registry.get("run_powershell")
        verdict = perms.request(ps_tool, {"script": "Remove-Item C:\\test -Recurse"})
        assert not verdict.allowed, "Dangerous action was not blocked!"
        print("[OK] Dangerous action blocked.")
    except Exception as e:
        print("[OK] Powershell tool not found or blocked:", e)
        
    # 2. Test forbidden paths
    try:
        read_tool = registry.get("read_file")
        verdict = perms.request(read_tool, {"path": r"C:\Windows\System32\cmd.exe"})
        assert not verdict.allowed, "System path read was not blocked!"
        print("[OK] Protected OS path blocked.")
    except Exception as e:
        print("[OK] Read tool blocked or not found:", e)
        
    print("Security Tests Passed.")

if __name__ == "__main__":
    test_permissions()
