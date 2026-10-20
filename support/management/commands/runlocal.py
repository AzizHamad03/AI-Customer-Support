import os
import signal
import subprocess
import sys
from time import sleep

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


def signal_process_group(process, signum):
    try:
        os.killpg(process.pid, signum)
    except ProcessLookupError:
        # The process group has already stopped.
        pass


def stop_processes(processes):
    # Ask both processes to stop.
    for _, process in processes:
        signal_process_group(process, signal.SIGINT)

    # Give them time to exit normally.
    for _, process in processes:
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass

    # Clean up any remaining processes, including server reload children.
    for _, process in processes:
        signal_process_group(process, signal.SIGKILL)
        process.wait()


class Command(BaseCommand):
    help = "Run the local web server and document worker together."

    # The web server performs Django's normal system checks.
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument(
            "addrport",
            nargs="?",
            default="127.0.0.1:8000",
            help="Web server address and port.",
        )

    def handle(self, *args, **options):
        manage_py = str(settings.BASE_DIR / "manage.py")

        environment = os.environ.copy()
        environment["PYTHONUNBUFFERED"] = "1"

        commands = [
            (
                "Web server",
                [
                    sys.executable,
                    manage_py,
                    "runserver",
                    options["addrport"],
                ],
            ),
            (
                "Document worker",
                [
                    sys.executable,
                    manage_py,
                    "process_document_jobs",
                ],
            ),
        ]

        processes = []

        try:
            for name, command in commands:
                process = subprocess.Popen(
                    command,
                    cwd=str(settings.BASE_DIR),
                    env=environment,
                    start_new_session=True,
                )
                processes.append((name, process))
                self.stdout.write(f"{name} started.")

            self.stdout.write(
                self.style.SUCCESS(
                    "Local application started. "
                    "Press Control+C to stop both processes."
                )
            )

            while True:
                for name, process in processes:
                    exit_code = process.poll()

                    if exit_code is not None:
                        raise CommandError(
                            f"{name} exited with code {exit_code}. "
                            "Both processes have been stopped. "
                            "Check the messages above."
                        )

                sleep(0.5)

        except KeyboardInterrupt:
            self.stdout.write(
                "\nStopping the web server and document worker..."
            )

        except OSError as exc:
            raise CommandError(
                f"Could not start the local application: {exc}"
            ) from exc

        finally:
            stop_processes(processes)