"""
TaskForge: A decorator-based scheduler for periodic and delayed task execution.

Features:
- Schedule tasks to run periodically (`every()`) or after a delay (`after()`).
- Pause, resume, stop, and dynamically edit tasks.
- Support for groups of tasks.
"""

'''
TODO:
- Groups
- Timeouts
- Dynamic task editing DONE
- Pause/resume DONE
- Stop (Cancel) DONE
- Priority
'''
from functools import wraps
import time
import threading
import random

__all__ = ["TaskForge"]

class TaskForge:
    def __init__(self):
        """
        Initializes the TaskForge scheduler.

        Attributes:
        - tasks: A dictionary containing all scheduled tasks and their properties.
        - groups: A dictionary mapping group names to lists of task names.
        - lock: A threading lock to ensure thread-safe access to tasks and groups.
        """
        self.tasks = {}
        self.groups = {}
        self.lock = threading.Lock()

    # Parse the interval string into a number of seconds
    def _parse_time(self, interval: str):
        """
        Converts a time string (e.g., '5s', '2m', '1h') to seconds.

        :param interval: A string representing the time interval.
        :return: The time in seconds as a float.
        :raises ValueError: If the interval format is invalid or interval is negatives.
        """
        if interval.endswith("s") and not interval.endswith("ms"):
            val = float(interval[:-1])
        elif interval.endswith("m"):
            val = float(interval[:-1]) * 60
        elif interval.endswith("h"):
            val = float(interval[:-1]) * 3600
        elif interval.endswith("d"):
            val = float(interval[:-1]) * 86400
        elif interval.endswith("ms"):
            val = float(interval[:-2]) / 1000
        else:
            raise ValueError("Invalid interval format")
        if val < 0:
            raise ValueError("Interval must be non-negative")
        return val

    # Expand list of tasks and groups into a list of tasks
    def _expand_targets(self, targets: list):
        expanded_targets = []
        for target in targets:
            if isinstance(target, str):
                if target in self.groups:
                    # If the target is a group name, add all tasks in that group
                    expanded_targets.extend(self.groups[target])
                else:
                    raise ValueError(f"Group '{target}' not found")
            else:
                expanded_targets.append(target.__name__ if callable(target) else target)
        return expanded_targets

    # Schedule a function to run every x units time
    def every(self, 
              interval: str, 
              delay: str= None, 
              jitter: str = None, 
              limit: int = None, 
              log: bool = False,
              group: str = None
              ):
        """
        Schedules a function to run periodically.

        :param interval: The time interval (e.g., '5s', '1m') between task executions.
        :param delay: An optional initial delay before the task starts (e.g., '2s').
        :param jitter: An optional random jitter applied to the interval (e.g., '500ms' gives the interval a ±0.5s random variation).
        :param limit: An optional limit on the number of executions.
        :param log: If True, logs task execution details to the console.
        :param group: An optional group name to group related tasks.
        :return: A decorator to wrap the target function.
        """
        interval = self._parse_time(interval)
        jitter = self._parse_time(jitter) if jitter else 0
        delay = self._parse_time(delay) if delay else 0

        def decorator(func):
            task_name = func.__name__
            with self.lock:
                if task_name in self.tasks:
                    raise NameError(f"Task '{task_name}' already exists.")

                @wraps(func)
                def wrapper(*args, **kwargs):
                    props = self.tasks[task_name]
                    time.sleep(props["delay"])
                    local_limit = props["limit"]

                    while local_limit is None or local_limit > 0:
                        with self.lock:
                            props = self.tasks[task_name]
                        match props["state"]:
                            case "paused":
                                time.sleep(0.1)
                                continue
                            case "stopped":
                                if props["log"]:
                                    print(f"Task '{func.__name__}' stopped")
                                break
                        try:
                            if props["log"]:
                                print(f"Executing task: {func.__name__}")
                            func(*args, **kwargs)
                            if props["log"]:
                                print(f"Task '{func.__name__}' executed successfully")

                        except Exception as e:
                            if props["log"]:
                                raise RuntimeError(f"Error in task '{func.__name__}': {e}")

                        jitter = props["jitter"]
                        jitter_amount = random.uniform(-jitter, jitter)
                        interval = props["interval"]
                        if interval + jitter_amount > 0:
                            time.sleep(interval + jitter_amount)

                        if local_limit is not None:
                            local_limit -= 1

                        if props["log"] and local_limit is not None:
                            print(f"Task '{func.__name__}' will run {local_limit} more times")

            with self.lock:
                self.tasks[task_name] = {
                        "function": wrapper,
                        "state": "active",
                        "interval": interval,
                        "delay": delay,
                        "jitter": jitter,
                        "limit": limit,
                        "log": log,
                        "group": group
                    }
                if group:
                    if group in self.groups:
                        self.groups[group].append(task_name)
                    else:
                        self.groups[group] = [task_name]
            return wrapper
        return decorator

    # Schedule a function to run once after x units time
    def after(self, 
              delay: str, 
              jitter: str = None, 
              log: bool = False
              ):
        """
        Schedules a function to run once after a delay.

        :param delay: The delay before the task starts (e.g., '5s').
        :param jitter: An optional random jitter applied to the delay (e.g., '500ms').
        :param log: If True, logs task execution details to the console.
        :return: A decorator to wrap the target function.
        """
        jitter = self._parse_time(jitter) if jitter else 0
        delay = self._parse_time(delay) if delay else 0

        def decorator(func):
            task_name = func.__name__

            @wraps(func)
            def wrapper(*args, **kwargs):
                props = self.tasks[task_name]
                jitter = props["jitter"]
                jitter_amount = random.uniform(-jitter, jitter)
                delay = props["delay"]
                if delay + jitter_amount > 0:
                    time.sleep(delay + jitter_amount)

                try:
                    if props["log"]:
                        print(f"Executing task: {func.__name__}")
                    func(*args, **kwargs)
                    if props["log"]:
                        print(f"Task '{func.__name__}' executed successfully")

                except Exception as e:
                    if props["log"]:
                        raise RuntimeError(f"Error in task '{func.__name__}': {e}")

            self.tasks[task_name] = {
                "function": wrapper,
                "state": "active",
                "delay": delay,
                "jitter": jitter,
                "log": log,
            }
            return wrapper
        return decorator

    # Simplified version of the edit function to modify a task's state
    def _set_state(self, func, state: str):
        task_name = func.__name__
        with self.lock:
            if task_name in self.tasks:
                self.tasks[task_name]["state"] = state
            else:
                raise ValueError(f"Task '{task_name}' not found")

    # Pause a specific task
    def pause(self, func):
        """
        Pauses a scheduled task.

        :param func: The task function to pause.
        """
        self._set_state(func, "paused")
        
    # Resume a specific task
    def resume(self, func):
        """
        Resumes a paused task.

        :param func: The task function to resume.
        """
        self._set_state(func, "active")

    # Stop a specific task
    def stop(self, func):
        """
        Stops a running task permanently.

        :param func: The task function to stop.
        """
        self._set_state(func, "stopped")

    # Edit property/properties of a specific task
    def edit(self, func, updates: dict):
        """
        Edits properties of a scheduled task.

        :param func: The task function to edit.
        :param updates: A dictionary containing property-value pairs to update.
        :raises ValueError: If the task or property is not found.
        """
        task_name = func.__name__
        with self.lock:
            if task_name in self.tasks:
                for prop, value in updates.items():
                    if prop not in self.tasks[task_name]:
                        raise ValueError(f"Property '{prop}' does not exist for task '{task_name}'.")
                    
                    if prop == "group":
                        # Handle group changes
                        old_group = self.tasks[task_name].get("group")
                        if old_group:
                            self.groups[old_group].remove(task_name)
                            if not self.groups[old_group]:  # Remove empty group
                                del self.groups[old_group]
                        if value:
                            if value not in self.groups:
                                self.groups[value] = []
                            self.groups[value].append(task_name)

                    if prop in ["delay", "interval", "jitter"]:
                        parsed_val = self._parse_time(value)
                        self.tasks[task_name][prop] = parsed_val
                    else:
                        self.tasks[task_name][prop] = value
            else:
                raise ValueError(f"Task '{task_name}' not found.")

    # Run task/s
    def run(self, 
            blocking: bool = True, 
            targets: list = None,
            args: dict = None
            ):
        """
        Runs all scheduled tasks or a subset of tasks.

        :param blocking: If True, blocks until all tasks finish execution.
        :param targets: A list of specific tasks or groups to run.
        :param args: A dictionary mapping task names to argument lists.
        """
        with self.lock:
            targets = self._expand_targets(targets) if targets else list(self.tasks.keys())

        def run_tasks():
            threads = []
            for task in targets:
                with self.lock:
                    if task in self.tasks:
                        task_args = args.get(task, []) if args else []  # Get arguments for the task if any
                        if not isinstance(task_args, (list, tuple)):
                            raise ValueError(f"Arguments for task '{task}' must be a list or tuple")
                        
                        thread = threading.Thread(target=self.tasks[task]["function"], args=task_args)
                        thread.daemon = True
                        thread.start()
                        threads.append(thread)
                    else:
                        raise ValueError(f"Task '{task}' not found.")
            for thread in threads:
                thread.join()

        if blocking:
            run_tasks()
        else:
            threading.Thread(target=run_tasks, daemon=True).start()

# Initialize the scheduler
scheduler = TaskForge()