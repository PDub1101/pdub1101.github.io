#!/usr/bin/env python3
"""
Master Unified Portfolio Sync (Hybrid Laptop + Cloud Failover)
Orchestrates CourtVision, Market Insight ($7K Stock Model), and DealScout:
1. Injects unified local .env credentials into all child pipelines
2. Runs Pre-Flight Cloud State Guard (pulls newer remote GitHub state before computing)
3. Executes each model inside an isolated try/except block with UTF-8 encoding
4. Mirrors updated outputs across all local workspaces and pdub1101.github.io
5. Executes single-commit atomic Git Tree deployments (SHA-diffed) across all 4 repos
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any, Optional

import requests

# ==============================================================================
# WORKSPACE PATHS & CONSTANTS
# ==============================================================================
MASTER_DIR = Path(r"C:\Users\pwgmc\Projects\pdub1101.github.io")
COURTVISION_DIR = Path(r"c:\Users\pwgmc\Downloads\CourtVision_NBA_Predictor")
MARKET_INSIGHT_DIR = Path(r"C:\Users\pwgmc\Projects\market-insight")
SHARP_NEWTON_DIR = Path(r"c:\Users\pwgmc\Documents\antigravity\sharp-newton")
DEALSCOUT_DIR = Path(r"c:\Users\pwgmc\Downloads\DealScout_Price_Tracker")

TOKEN_CANDIDATES = [
    SHARP_NEWTON_DIR / ".github_token",
    MARKET_INSIGHT_DIR / ".github_token",
]
ENV_SOURCES = [
    SHARP_NEWTON_DIR / ".env",
    DEALSCOUT_DIR / ".env",
    COURTVISION_DIR / ".env",
    MARKET_INSIGHT_DIR / ".env",
]

LOG_DIR = MASTER_DIR / "logs"
LOG_FILE = LOG_DIR / "master_sync.log"
GITHUB_OWNER = "PDub1101"

REPO_FILES: dict[str, tuple[Path, list[str]]] = {
    "court-vision": (
        COURTVISION_DIR,
        [
            "index.html",
            "app.js",
            "courtvision_data.js",
            "docs/index.html",
            "docs/app.js",
            "docs/courtvision_data.js",
            "docs/.nojekyll",
            "README.md",
            "requirements.txt",
            "update_model.py",
            ".gitignore",
            ".nojekyll",
            ".github/workflows/daily_courtvision.yml",
            "data/bankroll_state.json",
            "data/decision_basis.json",
            "data/courtvision_data.js",
            "src/data_fetcher.py",
            "src/quant_model.py",
            "src/gemini_veto.py",
            "src/bankroll_manager.py",
            "src/grader.py",
            "src/forecaster.py",
        ],
    ),
    "market-insight": (
        MARKET_INSIGHT_DIR,
        [
            "portfolio_data.js",
            "portfolio_state.json",
            "model_memory.json",
            "update_model.py",
            "README.md",
            ".nojekyll",
            ".github/workflows/daily_update.yml",
        ],
    ),
    "deal-scout": (
        DEALSCOUT_DIR,
        [
            "deals_data.js",
            "README.md",
            "scout_deals.py",
            "config/watchlist.json",
            "data/deals_data.json",
            "data/deal_history.json",
            "data/seed_history.py",
            "engine/percentile.py",
            "engine/gemini_auditor.py",
            "scouts/flight_scout.py",
            "frontend/deals_data.js",
            ".github/workflows/daily_scout.yml",
            ".nojekyll",
        ],
    ),
    "pdub1101.github.io": (
        MASTER_DIR,
        [
            "index.html",
            "Paul_Gibson_Resume.pdf",
            "README.md",
            "DESIGN.md",
            "master_daily_sync.py",
            "court-vision/index.html",
            "court-vision/app.js",
            "court-vision/courtvision_data.js",
            "market-insight/index.html",
            "market-insight/portfolio_data.js",
            "market-insight/portfolio_state.json",
            "market-insight/model_memory.json",
            "deal-scout/index.html",
            "deal-scout/deals_data.js",
        ],
    ),
}


# ==============================================================================
# LOGGING & ENVIRONMENT HELPERS
# ==============================================================================
def setup_logging() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("MasterDailySync")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    return logger


def load_token() -> str:
    for p in TOKEN_CANDIDATES:
        if p.exists():
            tok = p.read_text(encoding="utf-8").strip()
            if tok:
                return tok
    raise FileNotFoundError("GitHub token not found in expected locations.")


def build_unified_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    for env_path in ENV_SOURCES:
        if not env_path.exists():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and v and not env.get(k):
                env[k] = v
    return env


def gh_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "MasterDailySync/1.0",
    }


def fetch_remote_file_bytes(repo: str, rel_path: str, headers: dict[str, str]) -> Optional[bytes]:
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{repo}/contents/{rel_path}?ref=main"
    resp = requests.get(url, headers=headers, timeout=15)
    if resp.status_code != 200:
        return None
    data = resp.json()
    if "content" in data:
        return base64.b64decode(data["content"])
    if data.get("sha"):
        blob_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{repo}/git/blobs/{data['sha']}"
        b_resp = requests.get(blob_url, headers=headers, timeout=15)
        if b_resp.status_code == 200:
            return base64.b64decode(b_resp.json()["content"])
    return None


# ==============================================================================
# PRE-FLIGHT CLOUD STATE GUARD
# ==============================================================================
def _parse_iso_dt(val: str) -> dt.datetime:
    try:
        parsed = dt.datetime.fromisoformat(val.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed
    except Exception:
        return dt.datetime.min.replace(tzinfo=dt.timezone.utc)


def _parse_et_dt(val: str) -> dt.datetime:
    try:
        cleaned = val.replace(" ET", "").strip()
        return dt.datetime.strptime(cleaned, "%Y-%m-%d %I:%M %p")
    except Exception:
        return dt.datetime.min


def pull_latest_cloud_state(project: str, headers: dict[str, str], logger: logging.Logger) -> None:
    if project == "courtvision":
        remote_bytes = fetch_remote_file_bytes("court-vision", "data/bankroll_state.json", headers)
        if not remote_bytes:
            return
        remote_state = json.loads(remote_bytes.decode("utf-8"))
        local_path = COURTVISION_DIR / "data" / "bankroll_state.json"
        local_state = json.loads(local_path.read_text(encoding="utf-8")) if local_path.exists() else {}

        r_dt = _parse_iso_dt(remote_state.get("last_updated", ""))
        l_dt = _parse_iso_dt(local_state.get("last_updated", ""))
        r_count = len(remote_state.get("settled_bets", [])) + len(remote_state.get("active_bets", []))
        l_count = len(local_state.get("settled_bets", [])) + len(local_state.get("active_bets", []))
        r_settled = len(remote_state.get("settled_bets", []))
        l_settled = len(local_state.get("settled_bets", []))

        if (r_dt > l_dt and r_settled >= l_settled) or (r_count > l_count and r_settled >= l_settled):
            logger.info(f"[Guard][CourtVision] Remote cloud state is newer ({remote_state.get('last_updated')}); pulling down before run.")
            local_path.write_bytes(remote_bytes)
            basis_bytes = fetch_remote_file_bytes("court-vision", "data/decision_basis.json", headers)
            if basis_bytes:
                (COURTVISION_DIR / "data" / "decision_basis.json").write_bytes(basis_bytes)
            # Synchronize cloud courtvision_data.js payload as well
            data_bytes = fetch_remote_file_bytes("court-vision", "courtvision_data.js", headers)
            if data_bytes:
                for target_path in [
                    COURTVISION_DIR / "courtvision_data.js",
                    COURTVISION_DIR / "data" / "courtvision_data.js",
                    COURTVISION_DIR / "docs" / "courtvision_data.js",
                    MASTER_DIR / "court-vision" / "courtvision_data.js",
                ]:
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    target_path.write_bytes(data_bytes)
        else:
            logger.info("[Guard][CourtVision] Local state is current or ahead of remote.")

    elif project == "stocks":
        remote_bytes = fetch_remote_file_bytes("market-insight", "portfolio_state.json", headers)
        if not remote_bytes:
            return
        remote_state = json.loads(remote_bytes.decode("utf-8"))
        local_path = MARKET_INSIGHT_DIR / "portfolio_state.json"
        local_state = json.loads(local_path.read_text(encoding="utf-8")) if local_path.exists() else {}

        r_tab_date = (remote_state.get("day_tabs") or [{}])[-1].get("date", "")
        l_tab_date = (local_state.get("day_tabs") or [{}])[-1].get("date", "")
        r_lu = _parse_et_dt(remote_state.get("last_updated", ""))
        l_lu = _parse_et_dt(local_state.get("last_updated", ""))

        if (r_tab_date > l_tab_date) or (r_tab_date == l_tab_date and r_lu > l_lu):
            logger.info(f"[Guard][Stocks] Remote cloud state is newer ({r_tab_date} / {remote_state.get('last_updated')}); pulling down before run.")
            local_path.write_bytes(remote_bytes)
            for fname in ("model_memory.json", "portfolio_data.js"):
                fb = fetch_remote_file_bytes("market-insight", fname, headers)
                if fb:
                    (MARKET_INSIGHT_DIR / fname).write_bytes(fb)
        else:
            logger.info("[Guard][Stocks] Local state is current or ahead of remote.")

    elif project == "deals":
        remote_bytes = fetch_remote_file_bytes("deal-scout", "data/deal_history.json", headers)
        if not remote_bytes:
            return
        remote_hist = json.loads(remote_bytes.decode("utf-8"))
        local_path = DEALSCOUT_DIR / "data" / "deal_history.json"
        local_hist = json.loads(local_path.read_text(encoding="utf-8")) if local_path.exists() else {}

        r_date = remote_hist.get("last_updated_date", "")
        l_date = local_hist.get("last_updated_date", "")
        r_pts = sum(len(v) for v in remote_hist.get("flights", {}).values())
        l_pts = sum(len(v) for v in local_hist.get("flights", {}).values())

        if (r_date > l_date) or (r_date == l_date and r_pts > l_pts):
            logger.info(f"[Guard][DealScout] Remote rolling history has newer data ({r_date}, {r_pts} pts vs {l_pts}); pulling down.")
            local_path.write_bytes(remote_bytes)
        else:
            logger.info("[Guard][DealScout] Local history is current or ahead of remote.")


# ==============================================================================
# PIPELINE EXECUTION & CROSS-FOLDER MIRRORING
# ==============================================================================
def run_subprocess_step(
    name: str, script: str, cwd: Path, env: dict[str, str], logger: logging.Logger, timeout_sec: int = 240
) -> bool:
    logger.info(f"[{name}] Starting {script} in {cwd} ...")
    try:
        proc = subprocess.run(
            [sys.executable, script],
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_sec,
        )
        if proc.stdout:
            for line in proc.stdout.strip().splitlines()[-15:]:
                logger.info(f"[{name}]   {line}")
        if proc.returncode != 0:
            logger.error(f"[{name}] Failed with exit code {proc.returncode}")
            if proc.stderr:
                logger.error(f"[{name}] stderr: {proc.stderr[-1000:]}")
            return False
        logger.info(f"[{name}] Completed successfully.")
        return True
    except Exception as exc:
        logger.error(f"[{name}] Exception during execution: {exc}")
        logger.error(traceback.format_exc())
        return False


def mirror_outputs(project: str, logger: logging.Logger) -> None:
    if project == "courtvision":
        src = COURTVISION_DIR / "docs" / "courtvision_data.js"
        if src.exists():
            targets = [
                COURTVISION_DIR / "courtvision_data.js",
                COURTVISION_DIR / "data" / "courtvision_data.js",
                MASTER_DIR / "court-vision" / "courtvision_data.js",
            ]
            for dst in targets:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            logger.info("[Mirror][CourtVision] Synced courtvision_data.js to root, data/, and master hub.")

    elif project == "stocks":
        files = ("portfolio_state.json", "model_memory.json", "portfolio_data.js")
        for fname in files:
            src = MARKET_INSIGHT_DIR / fname
            if not src.exists():
                continue
            for dst_dir in (SHARP_NEWTON_DIR, MASTER_DIR / "market-insight"):
                dst_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst_dir / fname)
        logger.info("[Mirror][Stocks] Synced portfolio state, memory, and data across all 3 folders (preserving redesigned UI).")

    elif project == "deals":
        src = DEALSCOUT_DIR / "frontend" / "deals_data.js"
        if src.exists():
            for dst in (
                DEALSCOUT_DIR / "deals_data.js",
                MASTER_DIR / "deal-scout" / "deals_data.js",
            ):
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            logger.info("[Mirror][DealScout] Synced deals_data.js to root and master hub.")


# ==============================================================================
# ATOMIC SINGLE-COMMIT GIT TREE DEPLOYMENT
# ==============================================================================
def git_blob_sha(raw_bytes: bytes) -> str:
    return hashlib.sha1(f"blob {len(raw_bytes)}\0".encode("ascii") + raw_bytes).hexdigest()


def atomic_deploy_repo(
    repo_name: str, workspace: Path, file_list: list[str], headers: dict[str, str], logger: logging.Logger
) -> bool:
    api_base = f"https://api.github.com/repos/{GITHUB_OWNER}/{repo_name}"
    try:
        # 1. Get HEAD commit and base tree SHA
        r_ref = requests.get(f"{api_base}/git/refs/heads/main", headers=headers, timeout=15)
        r_ref.raise_for_status()
        head_sha = r_ref.json()["object"]["sha"]

        r_commit = requests.get(f"{api_base}/git/commits/{head_sha}", headers=headers, timeout=15)
        r_commit.raise_for_status()
        base_tree_sha = r_commit.json()["tree"]["sha"]

        # 2. Fetch recursive remote tree to compute exact SHA diffs
        r_tree = requests.get(f"{api_base}/git/trees/{base_tree_sha}?recursive=1", headers=headers, timeout=20)
        r_tree.raise_for_status()
        remote_blobs = {
            item["path"]: item["sha"]
            for item in r_tree.json().get("tree", [])
            if item.get("type") == "blob"
        }

        # 3. Identify changed files cleanly
        changed: list[tuple[str, bytes]] = []
        for rel_path in file_list:
            full_path = workspace / rel_path
            if not full_path.exists():
                continue
            raw_bytes = full_path.read_bytes()
            local_sha = git_blob_sha(raw_bytes)
            if remote_blobs.get(rel_path) != local_sha:
                changed.append((rel_path, raw_bytes))

        if not changed:
            logger.info(f"[Deploy][{repo_name}] All tracked files up-to-date (0 changes).")
            return True

        # 4. Create Git blobs (base64 preserves binary PDFs & exact byte signatures)
        tree_items = []
        for rel_path, raw_bytes in changed:
            b64_data = base64.b64encode(raw_bytes).decode("ascii")
            r_blob = requests.post(
                f"{api_base}/git/blobs",
                headers=headers,
                json={"content": b64_data, "encoding": "base64"},
                timeout=20,
            )
            r_blob.raise_for_status()
            blob_sha = r_blob.json()["sha"]
            tree_items.append({
                "path": rel_path,
                "mode": "100644",
                "type": "blob",
                "sha": blob_sha,
            })

        # 5. Build new Git tree, commit, and fast-forward main
        r_new_tree = requests.post(
            f"{api_base}/git/trees",
            headers=headers,
            json={"base_tree": base_tree_sha, "tree": tree_items},
            timeout=20,
        )
        r_new_tree.raise_for_status()
        new_tree_sha = r_new_tree.json()["sha"]

        now_label = dt.datetime.now().strftime("%Y-%m-%d %H:%M ET")
        file_summary = ", ".join(p for p, _ in changed[:4]) + ("..." if len(changed) > 4 else "")
        commit_msg = f"Master Portfolio Atomic Sync ({now_label}): {len(changed)} file(s) [{file_summary}]"

        r_new_commit = requests.post(
            f"{api_base}/git/commits",
            headers=headers,
            json={"message": commit_msg, "tree": new_tree_sha, "parents": [head_sha]},
            timeout=20,
        )
        r_new_commit.raise_for_status()
        new_commit_sha = r_new_commit.json()["sha"]

        r_patch = requests.patch(
            f"{api_base}/git/refs/heads/main",
            headers=headers,
            json={"sha": new_commit_sha},
            timeout=15,
        )
        r_patch.raise_for_status()
        logger.info(f"[Deploy][{repo_name}] Pushed single commit {new_commit_sha[:8]} ({len(changed)} file(s)).")
        return True
    except Exception as exc:
        logger.error(f"[Deploy][{repo_name}] Deployment failed: {exc}")
        logger.error(traceback.format_exc())
        return False


# ==============================================================================
# MAIN ORCHESTRATION
# ==============================================================================
def main() -> int:
    parser = argparse.ArgumentParser(description="Master Daily Sync for Paul Gibson Portfolio & Models")
    parser.add_argument("--all", action="store_true", help="Run all 3 projects (default)")
    parser.add_argument(
        "--project",
        choices=["courtvision", "stocks", "deals"],
        help="Run only one specific project",
    )
    parser.add_argument("--deploy-only", action="store_true", help="Skip execution and deploy current files only")
    args = parser.parse_args()

    logger = setup_logging()
    logger.info("=" * 70)
    logger.info("Master Portfolio Daily Sync Started")
    logger.info("=" * 70)

    token = load_token()
    headers = gh_headers(token)
    env = build_unified_env()

    if args.project:
        projects = [args.project]
    else:
        projects = ["courtvision", "stocks", "deals"]

    results: dict[str, bool] = {}

    if not args.deploy_only:
        for proj in projects:
            try:
                pull_latest_cloud_state(proj, headers, logger)
            except Exception as exc:
                logger.warning(f"[Guard][{proj}] Remote state check warning (continuing with local): {exc}")

            if proj == "courtvision":
                ok = run_subprocess_step("CourtVision", "update_model.py", COURTVISION_DIR, env, logger)
            elif proj == "stocks":
                ok = run_subprocess_step("Stocks", "update_model.py", MARKET_INSIGHT_DIR, env, logger)
            elif proj == "deals":
                ok = run_subprocess_step("DealScout", "scout_deals.py", DEALSCOUT_DIR, env, logger)
            else:
                ok = False

            results[proj] = ok
            if ok:
                try:
                    mirror_outputs(proj, logger)
                except Exception as exc:
                    logger.error(f"[Mirror][{proj}] Mirroring failed: {exc}")
            else:
                logger.warning(f"[{proj}] Skipping mirror because pipeline run did not complete successfully.")
    else:
        for proj in projects:
            mirror_outputs(proj, logger)
            results[proj] = True

    repos_to_deploy = []
    if "courtvision" in projects and (results.get("courtvision", False) or args.deploy_only):
        repos_to_deploy.append("court-vision")
    if "stocks" in projects and (results.get("stocks", False) or args.deploy_only):
        repos_to_deploy.append("market-insight")
    if "deals" in projects and (results.get("deals", False) or args.deploy_only):
        repos_to_deploy.append("deal-scout")
    repos_to_deploy.append("pdub1101.github.io")

    deploy_ok = True
    for repo in repos_to_deploy:
        ws, file_list = REPO_FILES[repo]
        ok = atomic_deploy_repo(repo, ws, file_list, headers, logger)
        if not ok:
            deploy_ok = False

    logger.info("=" * 70)
    logger.info(f"Pipeline results: {results} | Deploy OK: {deploy_ok}")
    logger.info("=" * 70)
    return 0 if (all(results.values()) and deploy_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
