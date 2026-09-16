"""Install the sotavpn bridge as a service.

The mode follows the account that runs this file
    Root runs it and the program goes where the system keeps its own
    programs, so the service starts at boot before anybody logs in. An
    ordinary user runs it and the program goes into that home directory, so
    the service starts at boot through linger. The exact places of both modes
    are the SYSTEM_INSTALL and USER_INSTALL sets of settings.py, and this file
    holds none of them itself.

What it copies
    The program file, the settings file, the readme, the licence, the
    certificates and this installer. Nothing else: the checks, the git
    history, the caches and the logs of the working copy stay out.

What it never does
    It never deletes anything: what it takes away goes to the trash when the
    machine has one, and is renamed beside itself when it has none. It never
    mentions the directory it was run from, so that directory can go away the
    moment it finishes.

How to run it
    python3 install_sotavpn_bridge.py install
    python3 install_sotavpn_bridge.py status
    python3 install_sotavpn_bridge.py uninstall

    Running install again is the way to update: the fresh settings and the
    fresh program replace the installed ones, the settings of the previous
    installation stay beside the new ones, and the service is restarted.
"""

import getpass
import importlib
import os
import shutil
import subprocess
import sys
import time

import settings

PROGRAM_DIRECTORY = os.path.dirname(os.path.abspath(__file__))

# The names of the actions this file knows.
ACTIONS = ("install", "status", "uninstall")

# The two modes. The account that runs this file decides which one is used.
SYSTEM_MODE = "system"
USER_MODE = "user"

# The name of the settings file, next to the program and on the target machine.
SETTINGS_FILE_NAME = "settings.py"

# What travels with the program into the code directory.
FILES_COPIED_WITH_THE_PROGRAM = ("README.md", "LICENSE")
DIRECTORIES_COPIED_WITH_THE_PROGRAM = ("certs",)

# How long to wait for the installed program to say that its ports are open.
SECONDS_TO_WAIT_FOR_THE_PROGRAM = 15

# The program itself, for the one rule that is already written there: how a
# file that is put aside is named.
the_program = importlib.import_module(settings.PROGRAM_NAME)


def say(message):
    """Tell the user what is happening, one line at a time."""
    print(message, flush=True)


def run_a_command(arguments):
    """Run one command of the system and answer its code, its output and its error."""
    finished = subprocess.run(arguments, capture_output=True, text=True, check=False)
    return finished.returncode, finished.stdout, finished.stderr


def mode_of_the_running_account():
    """The system mode when root runs this file, the user mode otherwise."""
    return SYSTEM_MODE if os.geteuid() == 0 else USER_MODE


def layout_of_the_mode(mode):
    """The set of install paths of one mode, taken from settings.py and never from here."""
    return settings.SYSTEM_INSTALL if mode == SYSTEM_MODE else settings.USER_INSTALL


def path_under_the_root(path, home_directory, root):
    """One path of the layout: ~ becomes the home directory, the root of a check is put in front."""
    if path.startswith("~"):
        path = os.path.join(home_directory, path.lstrip("~/"))
    return os.path.join(root, path.lstrip(os.sep))


def locations_of_the_installation(mode, home_directory=None, root=os.sep):
    """Every place one installation touches, as absolute paths."""
    home = home_directory or os.path.expanduser("~")
    layout = layout_of_the_mode(mode)
    code_directory = path_under_the_root(layout["code_directory"], home, root)
    settings_directory = path_under_the_root(layout["settings_directory"], home, root)
    return {
        "mode": mode,
        "code_directory": code_directory,
        "settings_file": os.path.join(settings_directory, SETTINGS_FILE_NAME),
        "unit_file": path_under_the_root(layout["unit_file"], home, root),
        "command_link": path_under_the_root(layout["command_link"], home, root),
        "temporary_directory": layout["temporary_directory"],
        "wanted_by": layout["wanted_by"],
        "program_file": os.path.join(code_directory, f"{settings.PROGRAM_NAME}.py"),
        "log_directory": os.path.join(code_directory, settings.LOGS_DIRECTORY),
    }


def unit_name_of(locations):
    """The name of the service, as systemd knows it."""
    return os.path.basename(locations["unit_file"])


def systemctl_of(locations):
    """The systemctl call of this mode: the user manager or the system one."""
    if locations["mode"] == USER_MODE:
        return ["systemctl", "--user"]
    return ["systemctl"]


def copy_one_file(source, target):
    """Copy one file, unless it already stands where it should: that is the update."""
    if os.path.abspath(source) == os.path.abspath(target):
        return False
    os.makedirs(os.path.dirname(target), exist_ok=True)
    shutil.copy2(source, target)
    return True


def copy_the_program(source_directory, code_directory):
    """Copy the program file, the readme, the licence, the certificates and this installer."""
    copied = []
    names = [f"{settings.PROGRAM_NAME}.py", os.path.basename(__file__)]
    for name in list(FILES_COPIED_WITH_THE_PROGRAM) + names:
        if copy_one_file(os.path.join(source_directory, name), os.path.join(code_directory, name)):
            copied.append(name)
    for name in DIRECTORIES_COPIED_WITH_THE_PROGRAM:
        source = os.path.join(source_directory, name)
        target = os.path.join(code_directory, name)
        if os.path.abspath(source) == os.path.abspath(target):
            continue
        shutil.copytree(source, target, dirs_exist_ok=True)
        copied.append(f"{name}/")
    return copied


def keep_the_previous_settings(settings_file):
    """Move the settings of the previous installation aside, its own moment in front."""
    if not os.path.exists(settings_file):
        return ""
    moment = time.strftime(settings.ARCHIVE_MOMENT_FORMAT, time.localtime(os.path.getmtime(settings_file)))
    number = 1
    kept = os.path.join(
        os.path.dirname(settings_file),
        the_program.name_of_the_archived_log(settings_file, moment, number),
    )
    while os.path.exists(kept):
        number += 1
        kept = os.path.join(
            os.path.dirname(settings_file),
            the_program.name_of_the_archived_log(settings_file, moment, number),
        )
    os.replace(settings_file, kept)
    return kept


def copy_the_settings(source_directory, settings_file):
    """Write the settings of the clone over the settings on this machine."""
    kept = keep_the_previous_settings(settings_file)
    copy_one_file(os.path.join(source_directory, SETTINGS_FILE_NAME), settings_file)
    return kept


def unit_file_text(locations):
    """The service that starts the program at boot, with the paths of this installation."""
    lines = [
        "[Unit]",
        f"Description={settings.PROGRAM_NAME} keeps a subscription address ready",
        "",
        "[Service]",
        "Type=simple",
        f"ExecStart={sys.executable} {locations['program_file']}",
        f"WorkingDirectory={locations['code_directory']}",
        f"Environment=TMPDIR={locations['temporary_directory']}",
        "Restart=on-failure",
        f"RestartSec={settings.SERVICE_RESTART_PAUSE_SECONDS}",
        "",
        "[Install]",
        f"WantedBy={locations['wanted_by']}",
        "",
    ]
    return "\n".join(lines)


def write_the_unit_file(locations):
    """Write the service file where systemd looks for it."""
    os.makedirs(os.path.dirname(locations["unit_file"]), exist_ok=True)
    with open(locations["unit_file"], "w", encoding="utf-8") as handle:
        handle.write(unit_file_text(locations))


def make_the_command_link(locations):
    """Point the command at the installed program, without touching a file of somebody else."""
    link = locations["command_link"]
    os.makedirs(os.path.dirname(link), exist_ok=True)
    if os.path.islink(link):
        os.unlink(link)
    elif os.path.exists(link):
        say(f"{link} is already there and is not a link of this installer, it stays as it is")
        return False
    os.symlink(locations["program_file"], link)
    return True


def enable_linger():
    """Let the user manager of this account run at boot, without a login."""
    account = getpass.getuser()
    code, out, err = run_a_command(["loginctl", "show-user", account, "-p", "Linger"])
    if "Linger=yes" in out:
        say(f"linger is already on for {account}, so the service starts at boot")
        return 0
    code, out, err = run_a_command(["loginctl", "enable-linger", account])
    if code != 0:
        say(f"linger could not be turned on: {err.strip() or out.strip()}")
        say("without linger the service starts at the next login of this account, not at boot")
    else:
        say(f"linger is on for {account}, so the service starts at boot")
    return code


def enable_the_service(locations):
    """Tell systemd about the service, then start it and make it start at boot."""
    command = systemctl_of(locations)
    run_a_command(command + ["daemon-reload"])
    code, out, err = run_a_command(command + ["enable", "--now", unit_name_of(locations)])
    if code != 0:
        say(f"systemd did not enable the service: {err.strip() or out.strip()}")
    return code


def state_of_the_service(locations):
    """The state systemd reports for the service, for example active."""
    code, out, err = run_a_command(systemctl_of(locations) + ["is-active", unit_name_of(locations)])
    return out.strip() or err.strip() or "unknown"


def journal_lines_of_the_installation(locations):
    """Every line the installed program has written in this run.

    The journal file belongs to one run: the program moves the journal of the
    previous run aside when it starts. There is therefore nothing to cut here,
    and the whole file is answered, so a reader sees the takeover of a busy
    port as well as the last line.
    """
    path = os.path.join(locations["log_directory"], settings.JOURNAL_FILE_NAME)
    try:
        with open(path, encoding="utf-8") as handle:
            return [line.rstrip("\n") for line in handle]
    except OSError:
        return []


def wait_for_the_program_to_start(locations, seconds=None):
    """Wait a moment for the installed program to say that its ports are open."""
    if seconds is None:
        seconds = SECONDS_TO_WAIT_FOR_THE_PROGRAM
    waited = 0
    while waited < seconds:
        if any("is listening on" in line for line in journal_lines_of_the_installation(locations)):
            return True
        time.sleep(1)
        waited += 1
    return False


def send_to_the_trash(path):
    """Take a file or a directory away without losing it: the trash, or a directory beside it.

    The name beside it ends with _removed and the path goes inside that
    directory, so a service file that is taken away never stays readable to
    systemd under its own name.
    """
    if not os.path.exists(path) and not os.path.islink(path):
        return ""
    if shutil.which("gio"):
        code, out, err = run_a_command(["gio", "trash", path])
        if code == 0:
            return "the trash"
    beside = os.path.join(os.path.dirname(path), f"{time.strftime(settings.ARCHIVE_MOMENT_FORMAT)}_removed")
    os.makedirs(beside, exist_ok=True)
    target = os.path.join(beside, os.path.basename(path))
    os.rename(path, target)
    return target


def say_where_the_program_stands(locations):
    """Tell the user where everything went and how to look at it."""
    say(f"the program stands in {locations['code_directory']}")
    say(f"the settings stand in {locations['settings_file']}")
    say(f"the logs lie in {locations['log_directory']}")
    say(f"the journal of this run is {os.path.join(locations['log_directory'], settings.JOURNAL_FILE_NAME)}")
    if locations["mode"] == USER_MODE:
        say(f"the state of the service: systemctl --user status {unit_name_of(locations)}")
        say(f"the lines of the service: journalctl --user -u {unit_name_of(locations)}")
    else:
        say(f"the state of the service: systemctl status {unit_name_of(locations)}")
        say(f"the lines of the service: journalctl -u {unit_name_of(locations)}")
    say(f"the plain address is http://127.0.0.1:{settings.HTTP_PORT}/")
    if settings.ENABLE_HTTPS:
        say(f"the secure address is https://127.0.0.1:{settings.HTTPS_PORT}/")
        say("its certificate is self signed, so a client needs permission to accept it")


def install_the_program(source_directory, locations):
    """Put everything in place, start the service and tell what happened."""
    say(f"installing from {source_directory}")
    say(f"the mode is {locations['mode']}, decided by the account that runs this installer")
    copied = copy_the_program(source_directory, locations["code_directory"])
    if copied:
        say(f"copied into {locations['code_directory']}: {', '.join(copied)}")
    else:
        say(f"the program already stands in {locations['code_directory']}, nothing was copied")
    kept = copy_the_settings(source_directory, locations["settings_file"])
    if kept:
        say(f"the settings of the previous installation stay as {kept}")
    say(f"the settings are {locations['settings_file']}")
    write_the_unit_file(locations)
    say(f"the service file is {locations['unit_file']}")
    if make_the_command_link(locations):
        say(f"the command is {locations['command_link']}")
    if locations["mode"] == USER_MODE:
        enable_linger()
    enable_the_service(locations)
    if wait_for_the_program_to_start(locations):
        say("the program runs and says that its ports are open")
    else:
        say("the program has not said yet that its ports are open, look at the journal in a few seconds")
    for line in journal_lines_of_the_installation(locations):
        print(line, flush=True)
    say_where_the_program_stands(locations)
    return 0


def status_of_the_installation(locations):
    """Tell what stands where and what the service is doing."""
    say(f"the mode of this installation is {locations['mode']}")
    for what, path in (
        ("the program file", locations["program_file"]),
        ("the settings", locations["settings_file"]),
        ("the service file", locations["unit_file"]),
        ("the command", locations["command_link"]),
    ):
        state = "is there" if os.path.exists(path) else "is not there"
        say(f"{what}: {path} {state}")
    say(f"the service {unit_name_of(locations)} is {state_of_the_service(locations)}")
    say(f"the logs lie in {locations['log_directory']}")
    for line in journal_lines_of_the_installation(locations):
        print(line, flush=True)
    return 0


def uninstall_the_program(locations):
    """Stop the service, take the installed files away, leave the settings and the logs."""
    say(f"uninstalling the {locations['mode']} installation")
    run_a_command(systemctl_of(locations) + ["disable", "--now", unit_name_of(locations)])
    for what, path in (
        ("the service file", locations["unit_file"]),
        ("the command", locations["command_link"]),
    ):
        where = send_to_the_trash(path)
        if where:
            say(f"{what} {path} went to {where}")
    where = send_to_the_trash(locations["code_directory"])
    if where:
        say(f"the program directory went to {where}")
    settings_directory = os.path.abspath(os.path.dirname(locations["settings_file"]))
    code_directory = os.path.abspath(locations["code_directory"])
    if settings_directory == code_directory or settings_directory.startswith(code_directory + os.sep):
        say("the settings and the logs went with the program directory, they are not lost")
    else:
        say(f"the settings stay in {settings_directory}, nothing of them was touched")
        say(f"the logs stay in {locations['log_directory']} as well")
    return 0


def main(arguments):
    """Do what the first argument asks, on the account that runs this file."""
    action = arguments[1] if len(arguments) > 1 else "install"
    if action not in ACTIONS:
        say(f"unknown action {action}, use one of: {', '.join(ACTIONS)}")
        return 2
    if not shutil.which("systemctl"):
        say("this machine has no systemctl, so there is nothing to install onto")
        return 1
    locations = locations_of_the_installation(mode_of_the_running_account())
    if action == "install":
        return install_the_program(PROGRAM_DIRECTORY, locations)
    if action == "status":
        return status_of_the_installation(locations)
    return uninstall_the_program(locations)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
