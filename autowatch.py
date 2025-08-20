import os
import subprocess
import time
import git
import requests
import psutil
import datetime

# --- Configuration ---
ROOT_PROJECT = os.environ.get("ROOT_PROJECT", "/home/arkiven4/Documents/Project/Vale")
AUTOWATCH_ENV = os.environ.get("AUTOWATCH_ENV", "dev")

FETCH_INTERVAL = 60 if AUTOWATCH_ENV == "dev" else 300 # 1 minute for dev, 5 minutes for prod

PROJECTS = [
    {
        "name": "cbm_vale_cbm",
        "repo_path": os.path.join(ROOT_PROJECT, "cbm_vale"),
        "branch_to_watch": "main",
        "script_to_run": "run_cbm.sh" if os.name != 'nt' else "run_cbm.bat",
        "github_repo": "arkiven4/cbm_vale",
        "process_name": "run_cbm.py",
        "max_retries": 3,
        "retry_delay": 10,
        "startup_period": 180, # 3 minutes
    },
    {
        "name": "cbm_vale_kpi",
        "repo_path": os.path.join(ROOT_PROJECT, "cbm_vale"),
        "branch_to_watch": "main",
        "script_to_run": "run_kpi.sh" if os.name != 'nt' else "run_kpi.bat",
        "github_repo": "arkiven4/cbm_vale",
        "process_name": "run_kpi.py",
        "max_retries": 3,
        "retry_delay": 10,
        "startup_period": 180, # 3 minutes
    },
    {
        "name": "tinymonitor-web",
        "repo_path": os.path.join(ROOT_PROJECT, "tinymonitor-web"),
        "branch_to_watch": "main",
        "script_to_run": "run.sh" if os.name != 'nt' else "run.bat",
        "github_repo": "arkiven4/tinymonitor-web",
        "process_name": "manage.py",
        "max_retries": 3,
        "retry_delay": 10,
        "startup_period": 180, # 3 minutes
    },
]

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# --- Functions ---

def get_latest_commit_hash(repo):
    """Gets the latest commit hash of the local repository."""
    return repo.head.commit.hexsha

def has_new_commit(repo, branch):
    """Checks if there is a new commit in the remote repository."""
    if not repo.remotes:
        print(f"No remotes found in the repository: {repo.working_dir}")
        return False
    try:
        remote = repo.remotes[0]
        print(f"Fetching from remote: {remote.url}")
        remote.fetch()
        local_hash = repo.head.commit.hexsha
        remote_hash = remote.refs[branch].commit.hexsha
        if local_hash != remote_hash:
            print(f"New commit found: {remote_hash}")
            return True
        else:
            print("No new commits.")
            return False
    except git.exc.GitCommandError as e:
        print(f"Error fetching remote: {e}")
        return False
    except IndexError:
        print(f"Branch {branch} not found on remote.")
        return False
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return False

def pull_latest_changes(repo, project):
    """Pulls the latest changes from the remote repository."""
    if not repo.remotes:
        print("No remotes found in the repository.")
        return False
    try:
        remote = repo.remotes[0]
        remote.pull()
        print(f"Successfully pulled latest changes for {project['name']}.")
        return True
    except git.exc.GitCommandError as e:
        print(f"Error pulling changes for {project['name']}: {e}")
        save_log_and_create_issue(project, "Failed to pull changes", str(e), "")
        return False

def is_process_running(process_name):
    """Checks if a process with the given name is currently running."""
    for proc in psutil.process_iter(['name', 'cmdline']):
        cmdline = proc.info.get('cmdline') or []
        if process_name in proc.info['name'] or process_name in " ".join(cmdline):
            return True
    return False

def stop_process(process_name):
    """Stops the currently running process."""
    if os.name == 'nt': # Windows
        try:
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                if process_name in " ".join(proc.info['cmdline'] or []):
                    subprocess.run(["taskkill", "/F", "/PID", str(proc.info['pid'])], check=True)
                    print(f"Process {process_name} stopped.")
                    return
        except subprocess.CalledProcessError as e:
            print(f"Error stopping process {process_name}: {e}")
    else: # Linux/macOS
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            cmdline = proc.info.get('cmdline') or []
            if process_name in proc.info['name'] or process_name in " ".join(cmdline):
                try:
                    p = psutil.Process(proc.info['pid'])
                    p.terminate()
                    p.wait()
                    print(f"Process {process_name} (PID: {proc.info['pid']}) stopped.")
                except psutil.NoSuchProcess:
                    print(f"Process {process_name} (PID: {proc.info['pid']}) already terminated.")
                except Exception as e:
                    print(f"Error stopping process {proc.info['pid']}: {e}")

def start_process(project):
    """Starts the specified script and returns the process object."""
    script_path = os.path.join(project["repo_path"], project["script_to_run"])
    try:
        if os.name == 'nt': # Windows
            if AUTOWATCH_ENV == "dev":
                process = subprocess.Popen([script_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            else:
                process = subprocess.Popen([script_path], creationflags=subprocess.CREATE_NO_WINDOW, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        else: # Linux/macOS
            process = subprocess.Popen(["bash", script_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        print(f"Successfully started script for {project['name']}.")
        return process
    except Exception as e:
        print(f"Error starting script for {project['name']}: {e}")
        return None

def create_github_issue(project, title, body):
    """Creates a new issue on GitHub."""
    if not GITHUB_TOKEN:
        print("GITHUB_TOKEN environment variable not set. Cannot create issue.")
        return

    url = f"https://api.github.com/repos/{project['github_repo']}/issues"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }
    data = {"title": title, "body": body, "labels": ["bug"]}
    try:
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 201:
            print(f"Successfully created GitHub issue for {project['name']}.")
        else:
            print(f"Failed to create GitHub issue for {project['name']}. Status code: {response.status_code}, Response: {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"Error creating GitHub issue for {project['name']}: {e}")

def save_log_and_create_issue(project, title, stdout, stderr):
    """Saves the log to a file and creates a GitHub issue."""
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f"{project['name']}_{timestamp}.log"
    log_filepath = os.path.join(LOG_DIR, log_filename)

    with open(log_filepath, "w") as f:
        f.write(f"--- STDOUT ---\n{stdout}\n")
        f.write(f"--- STDERR ---\n{stderr}\n")

    body = f"Error starting script for {project['name']}.\n\nLog file: `{log_filename}`\n\n--- STDOUT ---\n```\n{stdout}```\n\n--- STDERR ---\n```\n{stderr}```"
    create_github_issue(project, title, body)