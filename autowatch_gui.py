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
                "startup_failed": False,
            }
            for project in autowatch.PROJECTS
        }

    def run(self):
        """The main logic of the watcher thread."""
        repos = {project["name"]: autowatch.git.Repo(project["repo_path"]) for project in autowatch.PROJECTS}

        for project in autowatch.PROJECTS:
            process = autowatch.start_process(project)
            self.project_states[project["name"]]["process"] = process
            self.project_states[project["name"]]["start_time"] = time.time()

        while True:
            for project in autowatch.PROJECTS:
                project_name = project["name"]
                state = self.project_states[project_name]
                repo = repos[project_name]

                # Check for new commits
                if autowatch.has_new_commit(repo, project["branch_to_watch"]):
                    state["status"] = "Pulling"
                    if autowatch.pull_latest_changes(repo, project):
                        state["status"] = "Restarting Script"
                        if state["process"] and state["process"].poll() is None:
                            autowatch.stop_process(project["process_name"])
                        process = autowatch.start_process(project)
                        state["process"] = process
                        state["retry_count"] = 0
                        state["start_time"] = time.time()
                        state["startup_failed"] = False
                    else:
                        state["status"] = "Error Pulling"
                else:
                    state["status"] = "Watching"

                # Check process status
                if state["process"] and state["process"].poll() is not None:
                    # Process has terminated
                    if state["process"].returncode != 0:
                        # Process terminated with an error
                        if not state["startup_failed"]:
                            state["script_status"] = "Crashed during startup"
                            state["startup_failed"] = True
                            stdout, stderr = state["process"].communicate()
                            autowatch.save_log_and_create_issue(project, f"Failed to start {project_name}", stdout, stderr)
                        
                        if state["retry_count"] < project["max_retries"]:
                            current_time = time.time()
                            if current_time - state["last_retry_time"] > project["retry_delay"]:
                                state["script_status"] = f"Crashed. Retrying ({state['retry_count'] + 1}/{project['max_retries']})"
                                process = autowatch.start_process(project)
                                state["process"] = process
                                state["retry_count"] += 1
                                state["last_retry_time"] = time.time()
                                state["start_time"] = time.time()
                                state["startup_failed"] = False
                            else:
                                state["script_status"] = f"Crashed. Waiting to retry..."
                        else:
                            if state["script_status"] != "Failed to start. Max retries reached.":
                                state["script_status"] = "Failed to start. Max retries reached."
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
                        state["startup_failed"] = False
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
