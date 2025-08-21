import sys
import datetime
import time
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QGridLayout
from PyQt5.QtCore import QThread, pyqtSignal

import autowatch

class WatcherThread(QThread):
    """Runs the autowatch logic in a separate thread."""
    project_status_changed = pyqtSignal(str, str, str)

    def __init__(self):
        super().__init__()
        self.project_states = {
            project["name"]: {
                "retry_count": 0, 
                "last_retry_time": 0, 
                "process": None, 
                "status": "Starting...", 
                "script_status": "Starting...",
                "start_time": 0,
                "last_fetch_time": 0,
            }
            for project in autowatch.PROJECTS
        }

    def run(self):
        """The main logic of the watcher thread."""
        # Group projects by repo_path
        repos = {}
        for project in autowatch.PROJECTS:
            repo_path = project["repo_path"]
            if repo_path not in repos:
                repos[repo_path] = {
                    "repo_instance": autowatch.git.Repo(repo_path),
                    "projects": []
                }
            repos[repo_path]["projects"].append(project)

        # Initial start of all processes
        for repo_path, repo_data in repos.items():
            for project in repo_data["projects"]:
                process = autowatch.start_process(project)
                self.project_states[project["name"]]["process"] = process
                self.project_states[project["name"]]["start_time"] = time.time()

        while True:
            for repo_path, repo_data in repos.items():
                repo_instance = repo_data["repo_instance"]
                
                # Check for new commits for the repo
                # We only check one project's branch, assuming all projects in a repo share the same branch to watch
                project_for_branch_check = repo_data["projects"][0]
                current_time = time.time()

                # Use the state of the first project for timing the fetch
                first_project_name = project_for_branch_check["name"]
                if current_time - self.project_states[first_project_name]["last_fetch_time"] > autowatch.FETCH_INTERVAL:
                    self.project_states[first_project_name]["last_fetch_time"] = current_time
                    
                    if autowatch.has_new_commit(repo_instance, project_for_branch_check["branch_to_watch"]):
                        # If new commit is found, pull changes and restart all projects in this repo
                        if autowatch.pull_latest_changes(repo_instance, project_for_branch_check):
                            for project in repo_data["projects"]:
                                state = self.project_states[project["name"]]
                                state["status"] = "Restarting Script"
                                self.project_status_changed.emit(project["name"], state["status"], state["script_status"])
                                
                                if state["process"] and state["process"].poll() is None:
                                    autowatch.stop_process(project) # Pass the whole project object
                                
                                process = autowatch.start_process(project)
                                state["process"] = process
                                state["retry_count"] = 0
                                state["start_time"] = time.time()
                        else:
                            for project in repo_data["projects"]:
                                self.project_states[project["name"]]["status"] = "Error Pulling"
                    else:
                        for project in repo_data["projects"]:
                            self.project_states[project["name"]]["status"] = "Watching"

            # Process status checks (same as before, but iterated through all projects)
            for project in autowatch.PROJECTS:
                project_name = project["name"]
                state = self.project_states[project_name]

                # Check process status
                if state["process"] and state["process"].poll() is not None:
                    # Process has terminated
                    is_startup_failure = time.time() - state["start_time"] < project["startup_period"]
                    
                    if is_startup_failure:
                        if state["script_status"] != "Startup Failure":
                            state["script_status"] = "Startup Failure"
                            stdout, stderr = state["process"].communicate()
                            autowatch.save_log_and_create_issue(project, f"Startup Failure: {project_name}", stdout, stderr)
                    elif state["process"].returncode != 0:
                        # Process terminated with an error after startup
                        if state["retry_count"] < project["max_retries"]:
                            current_time = time.time()
                            if current_time - state["last_retry_time"] > project["retry_delay"]:
                                state["script_status"] = f"Crashed. Retrying ({state['retry_count'] + 1}/{project['max_retries']})"
                                process = autowatch.start_process(project)
                                state["process"] = process
                                state["retry_count"] += 1
                                state["last_retry_time"] = time.time()
                                state["start_time"] = time.time()
                            else:
                                state["script_status"] = f"Crashed. Waiting to retry..."
                        else:
                            if state["script_status"] != "Failed to start. Max retries reached.":
                                state["script_status"] = "Failed to start. Max retries reached."
                                stdout, stderr = state["process"].communicate()
                                autowatch.save_log_and_create_issue(project, f"Crash after retries: {project_name}", stdout, stderr)
                    else:
                        state["script_status"] = "Stopped"
                        state["process"] = None # Reset process
                elif state["process"] and time.time() - state["start_time"] > project["startup_period"]:
                    state["script_status"] = "Running"
                    state["retry_count"] = 0
                elif state["process"]:
                    state["script_status"] = "Starting up..."
                elif not state["process"] and state["retry_count"] < project["max_retries"]:
                    # Process is not running, and we can retry
                    current_time = time.time()
                    if current_time - state["last_retry_time"] > project["retry_delay"]:
                        state["script_status"] = f"Stopped. Retrying ({state['retry_count'] + 1}/{project['max_retries']})"
                        process = autowatch.start_process(project)
                        state["process"] = process
                        state["retry_count"] += 1
                        state["last_retry_time"] = time.time()
                        state["start_time"] = time.time()
                    else:
                        state["script_status"] = f"Stopped. Waiting to retry..."
                elif not state["process"]:
                     if state["script_status"] != "Failed to start. Max retries reached.":
                        state["script_status"] = "Failed to start. Max retries reached."

                self.project_status_changed.emit(project_name, state["status"], state["script_status"])

            self.msleep(5000)  # Check every 5 seconds

class App(QWidget):
    """The main application GUI."""
    def __init__(self):
        super().__init__()
        self.title = 'AutoWatch Status'
        self.project_widgets = {}
        self.initUI()

    def set_project_status(self, project_name, status, script_status):
        if project_name in self.project_widgets:
            self.project_widgets[project_name]["status_label"].setText(f"Status: {status}")
            self.project_widgets[project_name]["script_status_label"].setText(f"Script Status: {script_status}")
            self.project_widgets[project_name]["last_update_label"].setText(f"Last Update: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    def initUI(self):
        self.setWindowTitle(self.title)

        layout = QGridLayout()

        for i, project in enumerate(autowatch.PROJECTS):
            project_name = project["name"]
            
            name_label = QLabel(f"<b>{project_name}</b>")
            status_label = QLabel("Status: ")
            script_status_label = QLabel("Script Status: ")
            last_update_label = QLabel("Last Update: ")

            self.project_widgets[project_name] = {
                "status_label": status_label,
                "script_status_label": script_status_label,
                "last_update_label": last_update_label
            }

            layout.addWidget(name_label, i, 0)
            layout.addWidget(status_label, i, 1)
            layout.addWidget(script_status_label, i, 2)
            layout.addWidget(last_update_label, i, 3)

        self.setLayout(layout)

        self.thread = WatcherThread()
        self.thread.project_status_changed.connect(self.set_project_status)
        self.thread.start()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = App()
    ex.show()
    sys.exit(app.exec_())
